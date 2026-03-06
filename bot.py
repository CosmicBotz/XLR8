import os
import sys
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from config import BOT_TOKEN, OWNER_ID, LOG_CHANNEL_ID
from database import CosmicBotz
from middlewares.auth import AuthMiddleware
from handlers import start, admin, post
from handlers import filter as filter_handler
from handlers import group
from utils.scheduler import setup_scheduler, stop_scheduler

PORT         = int(os.environ.get("PORT", 8080))
WEBHOOK_URL  = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_PATH = "/webhook"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is missing!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL is missing!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
LOGGER = logging.getLogger("cosmicbotz")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

dp.message.middleware(AuthMiddleware())
dp.callback_query.middleware(AuthMiddleware())
dp.my_chat_member.middleware(AuthMiddleware())

dp.include_router(group.router)
dp.include_router(start.router)
dp.include_router(admin.router)
dp.include_router(post.router)
dp.include_router(filter_handler.router)

LOGGER.info("✅ All routers loaded")


async def on_startup(bot: Bot):
    await CosmicBotz.connect()
    setup_scheduler()

    webhook = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    await bot.set_webhook(url=webhook, drop_pending_updates=True)
    LOGGER.info(f"✅ Webhook set → {webhook}")

    startup_msg = "<b><blockquote>🤖 Auto Filter CosmicBotz Started ✅</blockquote></b>"

    # Notify owner
    try:
        await bot.send_message(chat_id=OWNER_ID, text=startup_msg)
    except Exception as e:
        LOGGER.warning(f"Could not notify owner: {e}")

    # Log to log channel
    if LOG_CHANNEL_ID:
        try:
            await bot.send_message(chat_id=LOG_CHANNEL_ID, text=startup_msg)
        except Exception as e:
            LOGGER.warning(f"Could not notify log channel: {e}")


async def on_shutdown(bot: Bot):
    LOGGER.info("⛔ Shutting down...")
    stop_scheduler()
    await CosmicBotz.close()
    await bot.session.close()
    LOGGER.info("✅ Shutdown complete.")


def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/",           lambda r: web.Response(text="Auto Filter CosmicBotz Running!"))
    app.router.add_get("/health",     lambda r: web.Response(text="OK"))
    app.router.add_get(WEBHOOK_PATH,  lambda r: web.Response(text="Webhook Alive"))

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    LOGGER.info(f"🌐 Starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
