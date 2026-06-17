import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import database as db
import payments
import access
from access import get_access_type
from config import BOT_TOKEN, TARIFFS, ADMIN_ID, WEBHOOK_PORT, LOG_FILE
from handlers import router
from scheduler import setup_scheduler


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


setup_logging()
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(router)


async def robokassa_result(request: web.Request) -> web.Response:
    data = await request.post()
    out_sum = data.get("OutSum")
    inv_id = data.get("InvId")
    signature = data.get("SignatureValue")

    logger.info("Robokassa callback InvId=%s OutSum=%s", inv_id, out_sum)

    if not out_sum or not inv_id or not signature:
        return web.Response(text="bad request", status=400)

    if not payments.check_result_signature(out_sum, inv_id, signature):
        logger.warning("Неверная подпись Robokassa для InvId=%s", inv_id)
        return web.Response(text="bad sign", status=400)

    inv_id_int = int(inv_id)
    payment = await db.get_payment(inv_id_int)

    if not payment:
        logger.warning("Платёж не найден: InvId=%s", inv_id)
        return web.Response(text=f"OK{inv_id}")

    if payment.status != "success":
        await db.mark_payment(inv_id_int, "success")

        user = await db.get_user(payment.telegram_id)
        access_type = get_access_type(user)

        new_end = await db.activate_subscription(payment.telegram_id, payment.tariff, inv_id_int)
        await access.grant_access(bot, payment.telegram_id, new_end, access_type)

        try:
            tariff_name = TARIFFS[payment.tariff]["name"]
            name = user.full_name if user else str(payment.telegram_id)
            await bot.send_message(
                ADMIN_ID,
                f"💰 Новая оплата!\n"
                f"Пользователь: {name} ({payment.telegram_id})\n"
                f"Тариф: {tariff_name}\n"
                f"Сумма: {payment.amount} тенге",
            )
        except Exception as exc:
            logger.warning("Не удалось уведомить админа: %s", exc)

    return web.Response(text=f"OK{inv_id}")


async def on_startup(app: web.Application) -> None:
    await db.init_db()
    setup_scheduler(bot)
    logger.info("База данных инициализирована, планировщик запущен")


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/robokassa/result", robokassa_result)
    app.on_startup.append(on_startup)
    return app


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Скопируйте .env.example в .env и заполните переменные.")

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()

    logger.info("Веб-сервер для Robokassa запущен на порту %s", WEBHOOK_PORT)
    logger.info("Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
