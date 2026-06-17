from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import TARIFFS, TARIFF_PROGRESSION, SITE_URL

USERS_PER_PAGE = 8


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="ℹ️ Узнать подробнее о клубе", url=SITE_URL)
    builder.button(text="💳 Выбрать тариф", callback_data="show_tariffs")
    builder.adjust(1)
    return builder.as_markup()


def tariffs_kb(allowed_tariffs: list[str] | None = None) -> InlineKeyboardMarkup:
    keys = allowed_tariffs or list(TARIFFS.keys())
    builder = InlineKeyboardBuilder()
    for key in keys:
        tariff = TARIFFS[key]
        text = f"{tariff['name']} — {tariff['price']:,} тенге".replace(",", " ")
        builder.button(text=text, callback_data=f"tariff_{key}")
    builder.adjust(1)
    return builder.as_markup()


def renewal_tariffs_kb(current_tariff: str | None) -> InlineKeyboardMarkup:
    allowed = TARIFF_PROGRESSION.get(current_tariff, list(TARIFFS.keys()))
    return tariffs_kb(allowed)


def pay_link_kb(url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=url)
    builder.adjust(1)
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="👥 Список участников", callback_data="admin_users_0")
    builder.adjust(1)
    return builder.as_markup()


def admin_users_kb(page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    max_page = max(0, (total - 1) // USERS_PER_PAGE)

    for i in range(USERS_PER_PAGE):
        offset = page * USERS_PER_PAGE + i
        if offset >= total:
            break
        builder.button(text=f"#{offset + 1}", callback_data=f"admin_user_idx_{offset}")

    nav = []
    if page > 0:
        nav.append(("◀️", f"admin_users_{page - 1}"))
    if page < max_page:
        nav.append(("▶️", f"admin_users_{page + 1}"))

    for label, data in nav:
        builder.button(text=label, callback_data=data)

    builder.button(text="🔙 Назад", callback_data="admin_menu")
    builder.adjust(4, 2, 1)
    return builder.as_markup()


def admin_user_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Продлить 1 мес", callback_data=f"admin_extend_{telegram_id}_1m")
    builder.button(text="➕ Продлить 6 мес", callback_data=f"admin_extend_{telegram_id}_6m")
    builder.button(text="➕ Продлить 12 мес", callback_data=f"admin_extend_{telegram_id}_12m")
    builder.button(text="⛔️ Приостановить", callback_data=f"admin_suspend_{telegram_id}")
    builder.button(text="🔙 К списку", callback_data="admin_users_0")
    builder.adjust(1)
    return builder.as_markup()
