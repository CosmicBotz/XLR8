"""
Search logic for filter titles.
Keeps database.py clean — only DB queries live here.
"""
import re
import unicodedata


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


async def run_search(query: str, db_instance) -> list:
    """
    Full search pipeline — strategies run in order, stop when results found.
    S1: Exact phrase (word boundary both ends)
    S2: Original query exact match
    S3: Acronym indexed lookup
    S4: All words present (2+ words, \b both ends)
    S5: Longest word fallback (2+ words)
    S6: Prefix fallback — "food war" → "Food Wars"
    S7: Fuzzy (rapidfuzz) — last resort for scrambled typos
    """
    norm_q_raw = _normalize(query.strip())

    # Load custom abbreviations, expand query
    ABBR = await db_instance.get_abbr_map()
    if norm_q_raw in ABBR:
        norm_q = _normalize(ABBR[norm_q_raw])
    else:
        tokens = norm_q_raw.split()
        norm_q = " ".join(ABBR.get(t, t) for t in tokens)

    # Block 1-2 char queries that aren't abbreviations
    if len(norm_q_raw) <= 2 and " " not in norm_q_raw and norm_q_raw not in ABBR:
        return []

    db    = db_instance.db()
    seen  = set()
    results = []

    async def _add(cursor):
        async for doc in cursor:
            oid = str(doc["_id"])
            if oid not in seen:
                seen.add(oid)
                results.append(doc)

    words = [w for w in norm_q.split() if len(w) >= 2]

    # S1: exact phrase with \b both ends
    try:
        pat = r"(?i)\b" + re.escape(norm_q) + r"\b"
        await _add(db.filters.find({"title_normalized": {"$regex": pat}}))
    except Exception:
        pass

    # S2: original query exact match
    if not results:
        try:
            pat = r"(?i)\b" + re.escape(query.strip()) + r"\b"
            await _add(db.filters.find({"title": {"$regex": pat}}))
        except Exception:
            pass

    # S3: acronym indexed lookup
    if not results and len(norm_q_raw) >= 2 and " " not in norm_q_raw:
        try:
            await _add(db.filters.find({"acronym": norm_q_raw}))
        except Exception:
            pass

    # S4: all words present (any order), 2+ words
    if len(words) >= 2 and len(results) < 5:
        try:
            wf = [{"title_normalized": {"$regex": r"(?i)\b" + re.escape(w) + r"\b"}} for w in words]
            await _add(db.filters.find({"$and": wf}))
        except Exception:
            pass

    # S5: longest word fallback, 2+ word queries
    if not results and len(words) >= 2:
        longest = max(words, key=len)
        if len(longest) >= 4:
            try:
                pat = r"(?i)\b" + re.escape(longest) + r"\b"
                await _add(db.filters.find({"title_normalized": {"$regex": pat}}))
            except Exception:
                pass

    # S6: prefix fallback — catches truncated words like "war" → "wars"
    if not results:
        for w in sorted(words, key=len, reverse=True):
            if len(w) >= 4:
                try:
                    await _add(db.filters.find({"title_normalized": {"$regex": r"(?i)\b" + re.escape(w)}}))
                    if results:
                        break
                except Exception:
                    pass

    # S7: fuzzy — only if everything above failed
    if not results:
        try:
            from rapidfuzz import fuzz
            all_docs = await db.filters.find(
                {}, {"title_normalized": 1, "title": 1}
            ).to_list(length=None)
            scored = []
            for doc in all_docs:
                score = fuzz.token_set_ratio(norm_q, doc.get("title_normalized", ""))
                if score >= 70:
                    scored.append((score, doc))
            scored.sort(key=lambda x: x[0], reverse=True)
            for _, doc in scored[:5]:
                oid = str(doc["_id"])
                if oid not in seen:
                    seen.add(oid)
                    full = await db.filters.find_one({"_id": doc["_id"]})
                    if full:
                        results.append(full)
        except ImportError:
            pass
        except Exception:
            pass

    return sorted(results, key=lambda x: x.get("title", ""))[:20]
