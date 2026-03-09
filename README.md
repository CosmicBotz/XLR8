# XLR8

A Python webhook service with MongoDB integration and media metadata support.

## Stack

- Python 3.11
- aiohttp (webhook server)
- Motor / MongoDB
- Pillow
- httpx

## Setup

```bash
git clone https://github.com/CosmicBotz/XLR8
cd XLR8
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Environment Variables

```env
BOT_TOKEN=
OWNER_ID=
MONGO_URI=
TMDB_API_KEY=
WEBHOOK_URL=
LOG_CHANNEL_ID=
AUTO_REVOKE_MINUTES=30
```

## Deployment

Set environment variables in your hosting dashboard and deploy.

Health check endpoint: `/health`
