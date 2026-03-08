"""
Thumbnail Processor — Website streaming style
"""

import io
import os
import logging
import aiohttp
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

_FONT_BOLD = "assets/fonts/DejaVuSans-Bold.ttf"
_FONT_REG  = "assets/fonts/DejaVuSans.ttf"
_SIZE      = (1280, 720)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch(url: str) -> Optional[Image.Image]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return Image.open(io.BytesIO(await r.read())).convert("RGBA")
    except Exception as e:
        logger.error(f"Image fetch failed: {e}")
    return None


async def _fetch_logo(file_id: str, bot) -> Optional[Image.Image]:
    """Download logo from Telegram by file_id."""
    try:
        file = await bot.get_file(file_id)
        buf  = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        return Image.open(buf).convert("RGBA")
    except Exception as e:
        logger.error(f"Logo fetch failed: {e}")
    return None


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(_FONT_BOLD, size)
        except Exception:
            return ImageFont.load_default()


def _wrap(text: str, font, draw, max_w: int) -> list:
    words = text.split()
    lines, line = [], []
    for w in words:
        if draw.textlength(" ".join(line + [w]), font=font) > max_w:
            if line:
                lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))
    return lines


# ── Watermark ─────────────────────────────────────────────────────────────────

def _draw_text_watermark(canvas: Image.Image, text: str) -> Image.Image:
    """
    Watermark — top-right clean dark pill, same right margin as bottom bar.
    """
    if not text:
        return canvas
    W, H   = canvas.size
    margin = 32          # matches episode card right margin
    font   = _font(18, bold=False)
    ov     = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od     = ImageDraw.Draw(ov)
    bbox   = od.textbbox((0, 0), text, font=font)
    px, py = 10, 5
    t_left, t_top, t_right, t_bottom = bbox
    tw = t_right - t_left
    th = t_bottom - t_top
    # Anchor from right edge with margin
    x     = W - tw - px * 2 - margin
    y     = margin
    bar_h = th + py * 2
    od.rectangle([x, y, x + tw + px * 2, y + bar_h], fill=(0, 0, 0, 185))
    od.text((x + px, y + py - t_top), text, font=font, fill=(255, 255, 255, 230))
    return Image.alpha_composite(canvas.convert("RGBA"), ov)


def _draw_logo_watermark(
    canvas: Image.Image,
    logo: Image.Image,
    text: str = "",
) -> Image.Image:
    """Logo image top-right — Anime Metrix style (red bar + logo + optional text)."""
    W, H   = canvas.size
    logo_h = 42          # smaller bar overall
    logo_w = int(logo.width * logo_h / logo.height)
    logo   = logo.resize((logo_w, logo_h), Image.LANCZOS)
    ov     = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od     = ImageDraw.Draw(ov)

    margin = 32   # matches episode card right margin
    if text:
        font        = _font(22)
        bbox        = od.textbbox((0, 0), text, font=font)
        # Use actual bbox coords for pixel-perfect centering
        t_left, t_top, t_right, t_bottom = bbox
        tw = t_right  - t_left
        th = t_bottom - t_top
        pad         = 8
        total_w     = logo_w + 8 + tw + pad * 2 + 4
        x           = W - total_w - margin
        y           = margin
        h           = max(logo_h, th) + pad * 2
        # Dark bg pill
        od.rectangle([x,     y, x + total_w, y + h], fill=(10, 10, 10, 185))
        # Red accent bar
        od.rectangle([x,     y, x + 4,       y + h], fill=(210, 25, 25, 255))
        # Logo — centred vertically in bar
        lx = x + 4 + pad
        ly = y + (h - logo_h) // 2
        ov.paste(logo, (lx, ly), logo)
        # Text — subtract bbox top offset so baseline aligns to true centre
        tx = lx + logo_w + 8
        ty = y + (h - th) // 2 - t_top
        od.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    else:
        # Just logo — small pill top-right
        x = W - logo_w - margin
        y = margin
        od.rectangle([x - 6, y - 4, x + logo_w + 6, y + logo_h + 4], fill=(10, 10, 10, 180))
        ov.paste(logo, (x, y), logo)

    return Image.alpha_composite(canvas.convert("RGBA"), ov)


# ── Top nav bar ───────────────────────────────────────────────────────────────

def _draw_top_nav(canvas: Image.Image, genres: str) -> Image.Image:
    """
    Genre tags — LEFT aligned, below watermark row, like AOT reference.
    Dot separator between items.
    """
    W, H  = canvas.size
    ov    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od    = ImageDraw.Draw(ov)
    items = [g.strip() for g in genres.split(",") if g.strip()][:5] if genres else []
    if not items:
        return canvas
    font  = _font(22, bold=False)
    dot   = "  •  "
    dot_w = int(od.textlength(dot, font=font))
    x     = 58      # same left margin as title
    y     = 108     # just above title_y=170, below watermark
    for i, g in enumerate(items):
        gw = int(od.textlength(g, font=font))
        od.text((x, y), g, font=font, fill=(210, 210, 210, 220))
        x += gw
        if i < len(items) - 1:
            od.text((x, y), dot, font=font, fill=(150, 150, 150, 160))
            x += dot_w
    return Image.alpha_composite(canvas.convert("RGBA"), ov)


# ── Card builder ──────────────────────────────────────────────────────────────

def _build_card(
    poster: Image.Image,
    backdrop: Optional[Image.Image],
    meta: dict,
) -> Image.Image:
    W, H = _SIZE

    # Very dark base
    canvas = Image.new("RGBA", (W, H), (12, 14, 20, 255))

    # Full blurred backdrop — near-black
    bg = (backdrop or poster).convert("RGBA").resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(10))
    bg = ImageEnhance.Brightness(bg).enhance(0.18)
    canvas.paste(bg.convert("RGBA"), (0, 0))

    # Character art — right side, tall
    char_img = poster.convert("RGBA")
    char_h   = int(H * 1.08)
    char_w   = int(char_h * char_img.width / char_img.height)
    char_img = char_img.resize((char_w, char_h), Image.LANCZOS)
    char_x   = W - char_w + int(char_w * 0.05)
    char_y   = -int(H * 0.05)

    # Fade left edge
    fade_w = int(char_w * 0.50)
    for i in range(fade_w):
        alpha = int(255 * (i / fade_w) ** 1.8)
        for yy in range(char_img.height):
            r2, g2, b2, a2 = char_img.getpixel((i, yy))
            char_img.putpixel((i, yy), (r2, g2, b2, min(a2, alpha)))

    # Fade bottom edge
    fade_bot = int(char_h * 0.15)
    for j in range(fade_bot):
        alpha = int(255 * (j / fade_bot))
        yy    = char_h - fade_bot + j
        if yy < char_h:
            for xi in range(char_w):
                r2, g2, b2, a2 = char_img.getpixel((xi, yy))
                char_img.putpixel((xi, yy), (r2, g2, b2, min(a2, alpha)))

    if char_x < W and char_y < H:
        canvas.paste(char_img, (char_x, char_y), char_img)

    # Left dark gradient for text legibility
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(grad)
    for i in range(W):
        alpha = max(0, int(210 - (i / W) * 230))
        gd.line([(i, 0), (i, H)], fill=(8, 10, 16, alpha))
    canvas = Image.alpha_composite(canvas, grad)

    draw = ImageDraw.Draw(canvas)

    # Extract metadata
    title    = meta.get("title", "").upper()
    episodes = str(meta.get("episodes", ""))
    seasons  = str(meta.get("seasons", ""))
    genres   = meta.get("genres", "")
    overview = meta.get("overview") or meta.get("synopsis", "")
    category = meta.get("_category", "")
    runtime  = meta.get("runtime", "")

    left_x = 58
    text_w = int(W * 0.46)

    # Title — auto-scale font so it always fits in 2 lines max
    def _best_font_size(title: str, max_w: int, draw) -> tuple:
        """Return (font, lines, line_height) that fits title in ≤2 lines."""
        for size in (72, 60, 50, 42, 34):
            f      = _font(size, bold=True)
            lines  = _wrap(title, f, draw, max_w)
            lh     = int(size * 1.18)
            if len(lines) <= 2:
                return f, lines[:2], lh
        # Last resort — 34px, allow 3 lines
        f = _font(34, bold=True)
        return f, _wrap(title, f, draw, max_w)[:3], int(34 * 1.18)

    tf, tlines, line_h = _best_font_size(title, text_w, draw)
    y = 170
    for ln in tlines:
        draw.text((left_x, y), ln, font=tf, fill=(255, 255, 255, 255))
        y += line_h
    y += 18

    # Description
    if overview:
        df = _font(23, bold=False)
        for ln in _wrap(overview, df, draw, text_w)[:4]:
            draw.text((left_x, y), ln, font=df, fill=(185, 185, 195, 210))
            y += 31
    y += 28

    # Buttons — vary by category
    btn_font = _font(22)
    btn_h    = 50

    if category == "manhwa":
        # READ NOW (red) only — no download for manhwa
        rn_label = "READ NOW"
        rn_w     = int(draw.textlength(rn_label, font=btn_font)) + 52
        draw.rectangle([left_x, y, left_x + rn_w, y + btn_h], fill=(210, 25, 25, 255))
        rn_tx = left_x + (rn_w - int(draw.textlength(rn_label, font=btn_font))) // 2
        draw.text((rn_tx, y + 14), rn_label, font=btn_font, fill=(255, 255, 255, 255))
    elif category == "movie":
        # DOWNLOAD (outline) + WATCH NOW (red)
        dl_label = "DOWNLOAD"
        dl_w     = int(draw.textlength(dl_label, font=btn_font)) + 52
        draw.rectangle([left_x, y, left_x + dl_w, y + btn_h], fill=(20, 20, 28, 230))
        draw.rectangle([left_x, y, left_x + dl_w, y + btn_h], outline=(255, 255, 255, 220), width=2)
        dl_tx = left_x + (dl_w - int(draw.textlength(dl_label, font=btn_font))) // 2
        draw.text((dl_tx, y + 14), dl_label, font=btn_font, fill=(255, 255, 255, 255))
        wn_label = "WATCH NOW"
        wn_x     = left_x + dl_w + 10
        wn_w     = int(draw.textlength(wn_label, font=btn_font)) + 52
        draw.rectangle([wn_x, y, wn_x + wn_w, y + btn_h], fill=(210, 25, 25, 255))
        wn_tx = wn_x + (wn_w - int(draw.textlength(wn_label, font=btn_font))) // 2
        draw.text((wn_tx, y + 14), wn_label, font=btn_font, fill=(255, 255, 255, 255))
    else:
        # anime / tvshow — DOWNLOAD (outline) + WATCH NOW (red)
        dl_label = "DOWNLOAD"
        dl_w     = int(draw.textlength(dl_label, font=btn_font)) + 52
        draw.rectangle([left_x, y, left_x + dl_w, y + btn_h], fill=(20, 20, 28, 230))
        draw.rectangle([left_x, y, left_x + dl_w, y + btn_h], outline=(255, 255, 255, 220), width=2)
        dl_tx = left_x + (dl_w - int(draw.textlength(dl_label, font=btn_font))) // 2
        draw.text((dl_tx, y + 14), dl_label, font=btn_font, fill=(255, 255, 255, 255))
        wn_label = "WATCH NOW"
        wn_x     = left_x + dl_w + 10
        wn_w     = int(draw.textlength(wn_label, font=btn_font)) + 52
        draw.rectangle([wn_x, y, wn_x + wn_w, y + btn_h], fill=(210, 25, 25, 255))
        wn_tx = wn_x + (wn_w - int(draw.textlength(wn_label, font=btn_font))) // 2
        draw.text((wn_tx, y + 14), wn_label, font=btn_font, fill=(255, 255, 255, 255))

    # Episode info card — bottom right
    card_w, card_h = 360, 128
    card_x = W - card_w - 32
    card_y = H - card_h - 32

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    cd   = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, card_w, card_h], radius=10, fill=(18, 20, 28, 230))
    cd.rounded_rectangle([0, 0, card_w, card_h], radius=10, outline=(55, 58, 78, 180), width=1)

    # Thumbnail inside card
    thumb_w, thumb_h = 100, card_h - 16
    thumb_x, thumb_y = card_w - thumb_w - 8, 8
    if backdrop or poster:
        th_img  = (backdrop or poster).convert("RGBA").resize((thumb_w, thumb_h), Image.LANCZOS)
        th_mask = Image.new("L", (thumb_w, thumb_h), 0)
        ImageDraw.Draw(th_mask).rounded_rectangle([0, 0, thumb_w, thumb_h], radius=6, fill=255)
        card.paste(th_img, (thumb_x, thumb_y), th_mask)

    # Episode display — smart handling for ongoing vs completed series
    cur_ep  = meta.get("current_episode") or meta.get("episode")
    status  = str(meta.get("status", "")).lower()
    total   = str(meta.get("episodes", ""))
    ongoing = status in ("ongoing", "airing", "currently airing", "returning series", "in production")

    if cur_ep and str(cur_ep) not in ("?", "N/A", "None", "0", ""):
        ep_num = str(cur_ep).zfill(2)
        ep_str = f"{ep_num}+" if ongoing else ep_num
    elif ongoing:
        # Ongoing but no current episode known
        ep_str = "N/A"
    elif total and total not in ("?", "N/A", "None", "0", ""):
        # Completed — show total as the episode count
        ep_str = str(total).zfill(2)
    else:
        ep_str = "N/A"

    # Card label varies by category
    if category == "manhwa":
        ep_label = f"Chapter - {ep_str}"
    elif category == "movie":
        ep_label = None   # movies don't show episode
    else:
        ep_label = f"Episode - {ep_str}"

    text_y = 14
    if ep_label:
        cd.text((16, text_y), ep_label, font=_font(28), fill=(255, 255, 255, 255))
        text_y += 38

    if seasons and seasons not in ("N/A", "None", "") and category not in ("movie", "manhwa"):
        cd.text((16, text_y), f"Season - {seasons.zfill(2)}", font=_font(22, bold=False), fill=(190, 190, 200, 220))
        text_y += 30

    rt_text = runtime if runtime and runtime not in ("N/A", "") else ("23m" if category == "anime" else "")
    if rt_text:
        cd.text((16, text_y), f"Duration - {rt_text}", font=_font(22, bold=False), fill=(190, 190, 200, 220))

    canvas.paste(card, (card_x, card_y), card)

    # Genre nav top-right
    canvas = _draw_top_nav(canvas, genres)

    return canvas


# ── Public API ────────────────────────────────────────────────────────────────

async def build_thumbnail(
    poster_url: Optional[str],
    backdrop_url: Optional[str] = None,
    watermark: str = "",
    watermark_logo_id: str = "",
    bot=None,
    meta: dict = {},
) -> bytes:
    os.makedirs("temp", exist_ok=True)

    poster = (await _fetch(poster_url)) if poster_url else None
    if poster is None:
        poster = Image.new("RGBA", (400, 600), (30, 30, 42, 255))
        ImageDraw.Draw(poster).text((60, 280), "No Image", fill=(120, 120, 140), font=_font(28))

    backdrop = (await _fetch(backdrop_url)) if backdrop_url else None
    card     = _build_card(poster, backdrop, meta)

    # Apply watermark last
    card = card.convert("RGBA")
    if watermark_logo_id and bot:
        logo = await _fetch_logo(watermark_logo_id, bot)
        if logo:
            card = _draw_logo_watermark(card, logo, watermark)
        else:
            card = _draw_text_watermark(card, watermark)
    elif watermark:
        card = _draw_text_watermark(card, watermark)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=93, optimize=True)
    return buf.getvalue()


async def process_custom_thumbnail(
    photo_bytes: bytes,
    watermark: str = "",
    watermark_logo_id: str = "",
    bot=None,
) -> bytes:
    img  = Image.open(io.BytesIO(photo_bytes)).convert("RGBA").resize(_SIZE, Image.LANCZOS)
    card = img.convert("RGBA")

    if watermark_logo_id and bot:
        logo = await _fetch_logo(watermark_logo_id, bot)
        if logo:
            card = _draw_logo_watermark(card, logo, watermark)
        else:
            card = _draw_text_watermark(card, watermark)
    elif watermark:
        card = _draw_text_watermark(card, watermark)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="JPEG", quality=93, optimize=True)
    return buf.getvalue()