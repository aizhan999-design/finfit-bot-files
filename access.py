import datetime
import logging

from aiohttp import ClientSession
from aiogram import Bot

import database as db
import getcourse
import keyboards as kb
from config import CHANNEL_ID, CHAT_ID, COURSE_LINK, TARIFFS

logger = logging.getLogger(__name__)


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else None


async def _getcourse_email(telegram_id: int) -> str | None:
    user = await db.get_user(telegram_id)
    if user and user.email:
        return user.email
    return None


async def _grant_getcourse(telegram_id: int) -> None:
    email = await _getcourse_email(telegram_id)
    if not email:
        logger.warning("GetCourse: нет email у user=%s", telegram_id)
        return

    user = await db.get_user(telegram_id)
    first, last = _split_name(user.full_name if user else None)

    async with ClientSession() as session:
        gc_id = await getcourse.grant_access(session, email, first, last)
        if gc_id:
            await db.set_getcourse_user_id(telegram_id, gc_id)


async def _revoke_getcourse(telegram_id: int) -> None:
    email = await _getcourse_email(telegram_id)
    if not email:
        return

    user = await db.get_user(telegram_id)
    gc_id = user.getcourse_user_id if user else None

    async with ClientSession() as session:
        await getcourse.revoke_access(session, email, gc_id)


async def _restore_getcourse(telegram_id: int) -> None:
    email = await _getcourse_email(telegram_id)
    if not email:
        return

    user = await db.get_user(telegram_id)
    first, _ = _split_name(user.full_name if user else None)

    async with ClientSession() as session:
        gc_id = await getcourse.restore_access(session, email, first)
        if gc_id:
            await db.set_getcourse_user_id(telegram_id, gc_id)


async def _add_to_telegram_chats(bot: Bot, telegram_id: int) -> str | None:
    invite_link = None
    targets = [cid for cid in (CHANNEL_ID, CHAT_ID) if cid]

    for chat_id in targets:
        try:
            invite = await bot.create_chat_invite_link(chat_id, member_limit=1)
            if not invite_link:
                invite_link = invite.invite_link
        except Exception as exc:
            logger.warning("Не удалось создать invite для %s user=%s: %s", chat_id, telegram_id, exc)

    return invite_link


async def _remove_from_telegram_chats(bot: Bot, telegram_id: int) -> None:
    for chat_id in [cid for cid in (CHANNEL_ID, CHAT_ID) if cid]:
        try:
            await bot.ban_chat_member(chat_id, telegram_id)
            await bot.unban_chat_member(chat_id, telegram_id)
        except Exception as exc:
            logger.warning("Не удалось удалить из %s user=%s: %s", chat_id, telegram_id, exc)


def get_access_type(user) -> str:
    if not user or user.status in ("new", None):
        return "new"
    if user.status == "paused":
        return "reactivation"
    return "renewal"


async def grant_access(
    bot: Bot,
    telegram_id: int,
    new_end: datetime.datetime,
    access_type: str,
) -> None:
    """
    access_type: 'new' | 'renewal' | 'reactivation'
    """
    if access_type == "renewal":
        await _restore_getcourse(telegram_id)
        text = (
            "✅ Оплата прошла успешно!\n\n"
            f"Ваша подписка продлена до <b>{new_end.strftime('%d.%m.%Y')}</b>.\n"
            "Спасибо что вы с нами! 🎉"
        )
        await _safe_send(bot, telegram_id, text)
        return

    if access_type == "reactivation":
        await _restore_getcourse(telegram_id)
        invite_link = await _add_to_telegram_chats(bot, telegram_id)

        text = (
            "✅ Оплата прошла успешно! Добро пожаловать обратно в Клуб FinFit 🎉\n\n"
            f"📚 Доступ к курсу «ФОРМУЛА старта»: {COURSE_LINK}\n"
        )
        if invite_link:
            text += f"\n💬 Ссылка для входа в закрытый канал и чат клуба (одноразовая):\n{invite_link}\n"
        text += f"\nВаша подписка действует до <b>{new_end.strftime('%d.%m.%Y')}</b>."
        await _safe_send(bot, telegram_id, text)
        return

    # Новый участник
    await _grant_getcourse(telegram_id)
    invite_link = await _add_to_telegram_chats(bot, telegram_id)

    text = (
        "✅ Оплата прошла успешно! Добро пожаловать в Клуб FinFit 🎉\n\n"
        "Что делать дальше:\n"
        f"1. Перейдите на курс «ФОРМУЛА старта»: {COURSE_LINK}\n"
    )
    if invite_link:
        text += f"2. Вступите в закрытый канал и чат клуба по ссылке (одноразовая):\n{invite_link}\n"
    else:
        text += "2. Менеджер добавит вас в закрытый канал и чат клуба.\n"

    text += f"\nВаша подписка действует до <b>{new_end.strftime('%d.%m.%Y')}</b>."
    await _safe_send(bot, telegram_id, text)


async def revoke_access(bot: Bot, telegram_id: int) -> None:
    await _remove_from_telegram_chats(bot, telegram_id)
    await _revoke_getcourse(telegram_id)

    user = await db.get_user(telegram_id)
    current_tariff = user.current_tariff if user else None

    text = (
        "⛔️ Ваша подписка на Клуб FinFit приостановлена.\n\n"
        "Хотите возобновить? Выберите тариф:\n"
    )
    for t in TARIFFS.values():
        text += f"— {t['name']}: {t['price']:,} тенге\n".replace(",", " ")

    await _safe_send(bot, telegram_id, text, reply_markup=kb.renewal_tariffs_kb(current_tariff))


async def _safe_send(bot: Bot, telegram_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
    except Exception as exc:
        logger.warning("Не удалось отправить сообщение user=%s: %s", telegram_id, exc)
