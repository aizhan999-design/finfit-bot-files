import logging
import re

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import database as db
import access
from access import get_access_type
import getcourse
import keyboards as kb
import payments
from config import TARIFFS, ADMIN_ID, SITE_URL, MANAGER_USERNAME

router = Router()
logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailForm(StatesGroup):
    waiting = State()


WELCOME_TEXT = (
    "👋 Привет! Добро пожаловать в <b>Клуб FinFit</b>!\n\n"
    "Это сообщество, где вы научитесь грамотно управлять финансами, "
    "копить, инвестировать и достигать финансовых целей.\n\n"
    f"Подробнее о клубе — на нашем сайте: {SITE_URL}\n\n"
    "Выберите действие 👇"
)


def _format_user_card(user) -> str:
    tariff_name = TARIFFS.get(user.current_tariff, {}).get("name", "—")
    status_names = {
        "new": "🆕 Новый",
        "active": "✅ Активна",
        "grace": "⚠️ Требуется оплата",
        "paused": "⛔️ Приостановлена",
    }
    end = user.subscription_end.strftime("%d.%m.%Y") if user.subscription_end else "—"
    username = f"@{user.username}" if user.username else "—"
    email = user.email or "—"

    return (
        f"<b>{user.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: {username}\n"
        f"Email: {email}\n"
        f"Тариф: {tariff_name}\n"
        f"Статус: {status_names.get(user.status, user.status)}\n"
        f"До: {end}"
    )



async def _start_payment(callback: CallbackQuery, tariff_key: str) -> None:
    tariff = TARIFFS[tariff_key]
    user = await db.get_user(callback.from_user.id)

    if getcourse.is_configured() and (not user or not user.email):
        await callback.message.answer(
            "📧 Для доступа к курсу на GetCourse укажите ваш email.\n"
            "Отправьте его одним сообщением:"
        )
        return

    inv_id = await db.create_payment(
        telegram_id=callback.from_user.id,
        tariff=tariff_key,
        amount=tariff["price"],
        is_recurring=True,
    )

    description = f"Подписка Клуб FinFit - {tariff['name']}"
    link = payments.generate_payment_link(inv_id, tariff["price"], description, is_recurring_first=True)

    text = (
        f"Тариф: <b>{tariff['name']}</b>\n"
        f"Сумма: <b>{tariff['price']:,} тенге</b>\n\n".replace(",", " ")
        + "Нажмите кнопку ниже для оплаты 👇\n\n"
        "После оплаты доступ будет выдан автоматически в течение нескольких минут."
    )
    await callback.message.answer(text, reply_markup=kb.pay_link_kb(link))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(WELCOME_TEXT, reply_markup=kb.main_menu_kb())


@router.callback_query(F.data == "show_tariffs")
async def show_tariffs(callback: CallbackQuery):
    text = "Выберите тариф 👇\n\n"
    for t in TARIFFS.values():
        text += f"• {t['name']} — {t['price']:,} тенге\n".replace(",", " ")

    await callback.message.edit_text(text, reply_markup=kb.tariffs_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def select_tariff(callback: CallbackQuery, state: FSMContext):
    tariff_key = callback.data.split("_", 1)[1]
    if tariff_key not in TARIFFS:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    if getcourse.is_configured() and (not user or not user.email):
        await state.set_state(EmailForm.waiting)
        await state.update_data(pending_tariff=tariff_key)
        await callback.message.answer(
            "📧 Для доступа к курсу на GetCourse укажите ваш email.\n"
            "Отправьте его одним сообщением:"
        )
        await callback.answer()
        return

    await _start_payment(callback, tariff_key)
    await callback.answer()


@router.message(EmailForm.waiting)
async def process_email(message: Message, state: FSMContext):
    email = message.text.strip().lower() if message.text else ""
    if not EMAIL_RE.match(email):
        await message.answer("Некорректный email. Попробуйте ещё раз:")
        return

    await db.set_user_email(message.from_user.id, email)
    data = await state.get_data()
    tariff_key = data.get("pending_tariff")
    await state.clear()

    if not tariff_key:
        await message.answer("Email сохранён ✅")
        return

    tariff = TARIFFS[tariff_key]
    inv_id = await db.create_payment(
        telegram_id=message.from_user.id,
        tariff=tariff_key,
        amount=tariff["price"],
        is_recurring=True,
    )
    description = f"Подписка Клуб FinFit - {tariff['name']}"
    link = payments.generate_payment_link(inv_id, tariff["price"], description, is_recurring_first=True)

    text = (
        f"Email сохранён ✅\n\n"
        f"Тариф: <b>{tariff['name']}</b>\n"
        f"Сумма: <b>{tariff['price']:,} тенге</b>\n\n".replace(",", " ")
        + "Нажмите кнопку ниже для оплаты 👇"
    )
    await message.answer(text, reply_markup=kb.pay_link_kb(link))


@router.message(Command("tarif"))
async def cmd_tarif(message: Message):
    text = "Тарифы Клуба FinFit:\n\n"
    for t in TARIFFS.values():
        text += f"• {t['name']} — {t['price']:,} тенге\n".replace(",", " ")
    await message.answer(text, reply_markup=kb.tariffs_kb())


@router.message(Command("status"))
async def cmd_status(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user.status == "new":
        await message.answer("У вас пока нет активной подписки. Используйте /tarif чтобы выбрать тариф.")
        return

    status_names = {
        "active": "✅ Активна",
        "grace": "⚠️ Требуется оплата",
        "paused": "⛔️ Приостановлена",
    }
    tariff_name = TARIFFS.get(user.current_tariff, {}).get("name", "—")
    text = f"Тариф: <b>{tariff_name}</b>\nСтатус: {status_names.get(user.status, user.status)}\n"
    if user.subscription_end:
        text += f"Действует до: {user.subscription_end.strftime('%d.%m.%Y')}\n"
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(f"Если у вас возникли вопросы — напишите менеджеру: {MANAGER_USERNAME}")


# ===================== АДМИН =====================

def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("🛠 Панель администратора", reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("🛠 Панель администратора", reply_markup=kb.admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return

    total = await db.count_users()
    by_tariff = await db.count_active_by_tariff()
    by_status = await db.count_by_status()

    text = f"📊 <b>Статистика</b>\n\n👥 Всего пользователей: {total}\n\n"
    text += "<b>По статусам:</b>\n"
    labels = {"new": "Новые", "active": "Активные", "grace": "Grace", "paused": "Приостановлены"}
    for key, label in labels.items():
        text += f"• {label}: {by_status.get(key, 0)}\n"

    text += "\n<b>Активные по тарифам:</b>\n"
    for key, t in TARIFFS.items():
        text += f"• {t['name']}: {by_tariff.get(key, 0)}\n"

    await callback.message.edit_text(text, reply_markup=kb.admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_"))
async def admin_users_list(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return

    page = int(callback.data.split("_")[-1])
    total = await db.count_users()
    users = await db.get_all_users(offset=page * kb.USERS_PER_PAGE, limit=kb.USERS_PER_PAGE)

    if not users and page > 0:
        await callback.answer()
        return

    lines = [f"👥 <b>Участники</b> (стр. {page + 1})\n"]
    for i, user in enumerate(users):
        idx = page * kb.USERS_PER_PAGE + i + 1
        name = user.full_name or user.username or str(user.telegram_id)
        tariff = TARIFFS.get(user.current_tariff, {}).get("name", "—")
        lines.append(f"{idx}. {name} — {tariff} ({user.status})")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=kb.admin_users_kb(page, total),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_idx_"))
async def admin_user_detail(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return

    offset = int(callback.data.split("_")[-1])
    users = await db.get_all_users(offset=offset, limit=1)
    if not users:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    user = users[0]
    await callback.message.edit_text(
        _format_user_card(user),
        reply_markup=kb.admin_user_actions_kb(user.telegram_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_extend_"))
async def admin_extend(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return

    parts = callback.data.split("_")
    telegram_id = int(parts[2])
    tariff_key = parts[3]

    user = await db.get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    access_type = get_access_type(user)
    new_end = await db.admin_extend_subscription(telegram_id, tariff_key)
    if not new_end:
        await callback.answer("Ошибка продления", show_alert=True)
        return

    await access.grant_access(callback.bot, telegram_id, new_end, access_type)

    user = await db.get_user(telegram_id)
    await callback.message.edit_text(
        f"✅ Подписка продлена до {new_end.strftime('%d.%m.%Y')}\n\n{_format_user_card(user)}",
        reply_markup=kb.admin_user_actions_kb(telegram_id),
    )
    await callback.answer("Продлено")


@router.callback_query(F.data.startswith("admin_suspend_"))
async def admin_suspend(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split("_")[-1])
    await db.set_status(telegram_id, "paused")
    await access.revoke_access(callback.bot, telegram_id)

    user = await db.get_user(telegram_id)
    await callback.message.edit_text(
        f"⛔️ Доступ приостановлен\n\n{_format_user_card(user)}",
        reply_markup=kb.admin_user_actions_kb(telegram_id),
    )
    await callback.answer("Приостановлено")
