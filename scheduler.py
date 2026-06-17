import datetime
import logging

from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

import database as db
import payments
import access
import keyboards as kb
from config import TARIFFS, ADMIN_ID

logger = logging.getLogger(__name__)


def _tariffs_text() -> str:
    lines = []
    for t in TARIFFS.values():
        lines.append(f"— {t['name']}: {t['price']:,} тенге".replace(",", " "))
    return "\n".join(lines)


REMINDER_3D_TEXT = (
    "⏰ Через 3 дня заканчивается Ваша подписка на Клуб FinFit.\n\n"
    "Хотите продолжить? Выберите удобный тариф:\n"
    "{tariffs}\n\n"
    "Выберите тариф 👇"
)

LAST_DAY_TEXT = (
    "🔔 Сегодня последний день вашей подписки на Клуб FinFit.\n\n"
    "Хотите продолжить? Выберите удобный тариф:\n"
    "{tariffs}\n\n"
    "Если вы не выберете тариф, будет выполнено автоматическое списание "
    "по текущему тарифу.\n\n"
    "Выберите тариф 👇"
)

FAILED_PAYMENT_TEXT = (
    "⚠️ Не удалось продлить подписку — оплата не прошла.\n\n"
    "Пожалуйста, обновите платёжные данные. У вас есть 24 часа, "
    "иначе доступ будет приостановлен."
)


async def check_reminders(bot: Bot) -> None:
    now = datetime.datetime.utcnow()
    window_start = now + datetime.timedelta(days=3)
    window_end = window_start + datetime.timedelta(hours=1)

    users = await db.get_users_for_reminder(window_start, window_end)
    text = REMINDER_3D_TEXT.format(tariffs=_tariffs_text())

    for user in users:
        try:
            await bot.send_message(
                user.telegram_id,
                text,
                reply_markup=kb.renewal_tariffs_kb(user.current_tariff),
            )
            await db.mark_reminder_sent(user.telegram_id)
            logger.info("Напоминание за 3 дня user=%s", user.telegram_id)
        except Exception as exc:
            logger.warning("Не удалось отправить напоминание user=%s: %s", user.telegram_id, exc)


async def check_last_day_reminders(bot: Bot) -> None:
    now = datetime.datetime.utcnow()
    users = await db.get_users_for_last_day_reminder(now)
    text = LAST_DAY_TEXT.format(tariffs=_tariffs_text())

    for user in users:
        try:
            await bot.send_message(
                user.telegram_id,
                text,
                reply_markup=kb.renewal_tariffs_kb(user.current_tariff),
            )
            await db.mark_last_day_reminder_sent(user.telegram_id)
            logger.info("Последнее напоминание user=%s", user.telegram_id)
        except Exception as exc:
            logger.warning("Не удалось отправить last-day user=%s: %s", user.telegram_id, exc)


async def check_autopay(bot: Bot) -> None:
    """Сценарий Б: 3 дня молчания после первого напоминания → автосписание."""
    now = datetime.datetime.utcnow()
    users = await db.get_users_for_autopay(now)

    async with ClientSession() as session:
        for user in users:
            if not user.current_tariff or user.current_tariff not in TARIFFS:
                await db.mark_autopay_attempted(user.telegram_id)
                continue

            tariff = TARIFFS[user.current_tariff]
            await db.mark_autopay_attempted(user.telegram_id)

            inv_id = await db.create_payment(
                telegram_id=user.telegram_id,
                tariff=user.current_tariff,
                amount=tariff["price"],
                is_recurring=True,
            )

            request_ok = False
            if user.last_inv_id:
                try:
                    description = f"Подписка Клуб FinFit - {tariff['name']}"
                    request_ok = await payments.charge_recurring(
                        session, inv_id, user.last_inv_id, tariff["price"], description
                    )
                except Exception as exc:
                    logger.exception("Ошибка автосписания user=%s: %s", user.telegram_id, exc)
                    request_ok = False

            if request_ok:
                logger.info("Запрос автосписания отправлен user=%s inv=%s", user.telegram_id, inv_id)
                continue

            await db.mark_payment(inv_id, "failed")
            await db.set_grace(user.telegram_id)

            try:
                await bot.send_message(user.telegram_id, FAILED_PAYMENT_TEXT)
            except Exception:
                pass

            logger.warning("Автосписание не прошло user=%s", user.telegram_id)


async def check_suspensions(bot: Bot) -> None:
    deadline = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    users = await db.get_grace_expired_users(deadline)

    for user in users:
        await db.set_status(user.telegram_id, "paused")
        await access.revoke_access(bot, user.telegram_id)

        try:
            name = user.full_name or user.username or str(user.telegram_id)
            await bot.send_message(
                ADMIN_ID,
                f"⛔️ Доступ приостановлен\nПользователь: {name} ({user.telegram_id})\n"
                f"Тариф: {TARIFFS.get(user.current_tariff, {}).get('name', '—')}",
            )
        except Exception:
            pass

        logger.info("Приостановлен доступ user=%s", user.telegram_id)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_reminders, "interval", hours=1, args=[bot], id="reminders_3d")
    scheduler.add_job(check_last_day_reminders, "interval", hours=1, args=[bot], id="reminders_last_day")
    scheduler.add_job(check_autopay, "interval", hours=1, args=[bot], id="autopay")
    scheduler.add_job(check_suspensions, "interval", hours=1, args=[bot], id="suspensions")
    scheduler.start()
    return scheduler
