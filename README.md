<div align="center">

# 🤖 Auto Filter CosmicBotz

**Telegram Auto Filter Bot** for Anime · TV Shows · Movies

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=flat&logo=telegram&logoColor=white)](https://aiogram.dev)
[![MongoDB](https://img.shields.io/badge/MongoDB-CosmicBotz-47A248?style=flat&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)

*TMDB Integration · Streaming-Style Thumbnails · Letter Index · Auto-Revoke Links · Group Verification · Webhook Mode*

</div>

---

## 📁 Project Structure

```
auto_filter_cosmicbotz/
├── bot.py              → Webhook entry (aiohttp + aiogram)
├── config.py           → Env vars + START_PICS list
├── database.py         → class Database / CosmicBotz singleton
├── Dockerfile          → Python 3.11-slim + DejaVu fonts
├── render.yaml         → Render deploy config (Docker runtime)
├── requirements.txt
├── .env.example
│
├── handlers/
│   ├── start.py        → /start /help /stats
│   ├── admin.py        → slots, admins, settings, watermark, delcontent
│   ├── post.py         → /addcontent TMDB wizard → log channel post
│   ├── filter.py       → letter index & title search → copy from log channel
│   └── group.py        → group join/verify lifecycle
│
├── keyboards/
│   └── inline.py       → all inline keyboards
│
├── services/
│   ├── tmdb.py         → TMDB search + details (poster + backdrop)
│   ├── thumbnail.py    → streaming-style 1280×720 thumbnail generator
│   ├── caption.py      → blockquote caption builder (reads DB settings)
│   └── link_gen.py     → single-use expiring invite links
│
├── middlewares/
│   └── auth.py         → owner / admin / group checks
│
└── utils/
    └── scheduler.py    → APScheduler (reserved for future tasks)
```

---

<details>
<summary><b>⚙️ Local Setup</b></summary>

```bash
git clone https://github.com/yourrepo/auto_filter_cosmicbotz
cd auto_filter_cosmicbotz
pip install -r requirements.txt
cp .env.example .env    # fill in your values
python bot.py
```

</details>

---

<details>
<summary><b>🚀 Render Deployment</b></summary>

1. Push code to **GitHub**
2. Create **New Web Service** on Render → connect your repo
3. Render auto-detects `render.yaml` (Docker runtime)
4. Set env vars in Render Dashboard:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `OWNER_ID` | Your Telegram user ID |
| `MONGO_URI` | MongoDB Atlas URI |
| `TMDB_API_KEY` | From themoviedb.org |
| `WEBHOOK_URL` | `https://your-app.onrender.com` |

5. Set **Health Check Path** → `/health`
6. Hit **Deploy** 🚀

> Dockerfile locks Python 3.11 + installs DejaVu fonts for thumbnail rendering.

</details>

---

<details>
<summary><b>🎬 How It Works</b></summary>

```
/addcontent
  → TMDB fetch (once only — poster + backdrop)
  → Generate streaming-style 1280×720 thumbnail
  → Post to LOG_CHANNEL with permanent invite link
  → Save message_id to DB index

User searches → taps title
  → bot.copy_message() from LOG_CHANNEL
  → attach fresh expiring invite link button
  → no TMDB calls ever again
```

</details>

---

<details>
<summary><b>🗄️ Database — CosmicBotz</b></summary>

Single `database.py` — one `class Database` instance shared across the entire bot.

```python
from database import CosmicBotz

await CosmicBotz.connect()
await CosmicBotz.add_filter(data)
await CosmicBotz.get_by_letter("N")
await CosmicBotz.verify_group(id)
await CosmicBotz.get_settings()
```

**Collections inside `CosmicBotz` db:**

| Collection | Purpose |
|---|---|
| `filters` | Anime / TV / Movie index + log channel message refs |
| `slots` | Channel posting slots (used for invite link generation) |
| `admins` | Admin user IDs |
| `settings` | Quality, audio, watermark, auto-revoke minutes |
| `groups` | Group verification records |

</details>

---

<details>
<summary><b>🌐 Group Verification</b></summary>

| Event | What happens |
|---|---|
| Bot added to group | Welcome message · owner notified in DM |
| `/verify` in group | Owner/admin unlocks all features |
| Unverified group | Only `/start` responds · rest silently ignored |
| `/verifygroup ID` | Verify any group remotely from DM |
| `/unverify` | Revoke group access |
| `/groups` | Owner sees all groups + pending list |

</details>

---

<details>
<summary><b>📋 Commands</b></summary>

**Owner** *(DM only)*
```
/addslot          Add a channel slot (for invite link generation)
/slots            View & manage slots
/removeslot       Remove a slot
/addcontent       Add anime/movie/tvshow via TMDB wizard
/addadmin         Add a bot admin
/removeadmin      Remove a bot admin
/admins           List all admins
/delcontent       Delete a title from the index
/setrevoke        Set invite link expiry time (minutes)
/setquality       Set default quality line in captions
/setaudio         Set default audio line in captions
/setcaption       View current caption settings
/setwatermark     Set text watermark on thumbnails
/setlogo          Reply to a photo → set logo watermark
/clearwatermark   Remove watermark
/settings         View all settings
/groups           List all groups
/verifygroup      Verify a group remotely
/stats            Bot statistics
```

**Admin** *(DM + verified groups)*
```
/addcontent  /delcontent  /slots  /verify  /stats
```

**Users** *(verified groups + DM)*
```
Send A–Z      → Browse index by letter
Send title    → Search by name
Tap result    → Bot copies log channel post with fresh invite link
Watch/Download → Single-use timed invite link (auto-expires)
```

</details>

---

<details>
<summary><b>🖼️ Thumbnail Generator</b></summary>

`services/thumbnail.py` — streaming-style card, 1280×720:

- **Background** — blurred dark TMDB backdrop
- **Character art** — poster on right with fade edges
- **Left panel** — title + overview + genre tags + action buttons
- **Bottom-right card** — episode / season / runtime info
- **Watermark** — text pill or logo image top-right (set via `/settings`)

Sources used per title:
- `poster_path` → portrait art (right side character)
- `backdrop_path` → wide cinematic bg (blurred dark background)

Both fetched from TMDB **once** at `/addcontent` time.

</details>

---

<details>
<summary><b>🖼️ Start Pictures</b></summary>

Add Telegram `file_id`s or image URLs to `START_PICS` in `config.py`.
Bot picks one randomly on each `/start` · falls back to text if empty or send fails.

```python
START_PICS: list[str] = [
    "https://example.com/banner.jpg",
    "AgACAgIAAxk...telegram_file_id...",
]
```

</details>

---

<details>
<summary><b>🔑 Environment Variables</b></summary>

```env
BOT_TOKEN=              # @BotFather
OWNER_ID=               # your Telegram user ID
MONGO_URI=              # MongoDB Atlas URI
TMDB_API_KEY=           # themoviedb.org/settings/api
WEBHOOK_URL=            # https://your-app.onrender.com
LOG_CHANNEL_ID=         # required — bot posts thumbnails here
AUTO_REVOKE_MINUTES=30  # invite link expiry default
```

</details>

---

<div align="center">
<sub>Built with ❤️ · Aiogram 3 · MongoDB · TMDB · Pillow · CosmicBotz</sub>
</div>
