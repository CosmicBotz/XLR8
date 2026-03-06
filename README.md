<div align="center">

# 🤖 Auto Filter CosmicBotz

**Telegram Auto Filter Bot** for Anime · TV Shows · Movies

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=flat&logo=telegram&logoColor=white)](https://aiogram.dev)
[![MongoDB](https://img.shields.io/badge/MongoDB-COSMICBOTZ-47A248?style=flat&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat&logo=render&logoColor=white)](https://render.com)

*TMDB Integration · Letter Index · Auto-Revoke Links · Group Verification · Webhook Mode*

</div>

---

## 📁 Project Structure

```
auto_filter_cosmicbotz/
├── bot.py              → Webhook entry (aiohttp + aiogram)
├── config.py           → Env vars + START_PICS list
├── database.py         → class Database / CosmicBotz singleton
├── render.yaml         → Render deploy config
├── requirements.txt
├── .env.example
│
├── handlers/
│   ├── start.py        → /start /help /stats
│   ├── admin.py        → slots, admins, settings
│   ├── post.py         → /addcontent TMDB wizard
│   ├── filter.py       → letter & title search
│   └── group.py        → group join/verify lifecycle
│
├── keyboards/
│   └── inline.py       → all inline keyboards
│
├── services/
│   ├── tmdb.py         → TMDB API (anime / tv / movie)
│   ├── caption.py      → caption builder
│   └── link_gen.py     → invite link create & revoke
│
├── middlewares/
│   └── auth.py         → owner / admin / group checks
│
└── utils/
    └── scheduler.py    → APScheduler (auto-revoke job)
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
3. Render auto-detects `render.yaml`
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

> Render injects `$PORT` automatically — bot reads it from `config.py`.
> Telegram POSTs updates to `/webhook` · `/health` prevents service restart.

</details>

---

<details>
<summary><b>🗄️ Database — COSMICBOTZ</b></summary>

Single `database.py` file — one `class Database` instance shared across the entire bot.

```python
from database import CosmicBotz

await CosmicBotz.connect()          # startup
await CosmicBotz.add_filter(data)   # index a title
await CosmicBotz.get_by_letter("N") # browse index
await CosmicBotz.verify_group(id)   # group auth
```

**Collections inside `COSMICBOTZ` db:**

| Collection | Purpose |
|---|---|
| `filters` | Anime / TV / Movie index |
| `slots` | Channel posting slots |
| `admins` | Admin user IDs |
| `posts` | Invite links + TTL expiry |
| `settings` | Owner settings |
| `groups` | Group verification records |

</details>

---

<details>
<summary><b>🌐 Group Verification</b></summary>

| Event | What happens |
|---|---|
| Bot added to group | Welcome message sent · owner notified in DM |
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
/addslot        Add a channel posting slot
/slots          View & manage slots
/removeslot     Remove a slot
/addcontent     Post anime/movie/tvshow via TMDB wizard
/addadmin       Add a bot admin
/removeadmin    Remove a bot admin
/admins         List all admins
/setrevoke      Set invite link expiry time
/settings       View all settings
/groups         List all groups
/verifygroup    Verify a group remotely
/stats          Bot statistics
```

**Admin** *(DM + verified groups)*
```
/addcontent  /slots  /verify  /stats
```

**Users** *(verified groups + DM)*
```
Send A–Z      → Browse index by letter
Send title    → Search by name
Tap result    → Jump to channel post
Watch/Download → Timed invite link (auto-revokes)
```

</details>

---

<details>
<summary><b>🖼️ Start Pictures</b></summary>

Add Telegram `file_id`s or image URLs to `START_PICS` in `config.py`.  
Bot picks one **randomly** on each `/start` · falls back to text if list is empty or send fails.

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
BOT_TOKEN=          # @BotFather
OWNER_ID=           # your Telegram user ID (@userinfobot)
MONGO_URI=          # MongoDB Atlas connection string
TMDB_API_KEY=       # themoviedb.org/settings/api
WEBHOOK_URL=        # https://your-app.onrender.com
LOG_CHANNEL_ID=     # optional log channel
AUTO_REVOKE_MINUTES=30
```

</details>

---

<div align="center">
<sub>Built with ❤️ · Powered by Aiogram 3 · MongoDB COSMICBOTZ · TMDB</sub>
</div>
