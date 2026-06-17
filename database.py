import datetime
import logging

from sqlalchemy import BigInteger, String, DateTime, Numeric, Boolean, select, update, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import DB_URL, TARIFFS

logger = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    getcourse_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    current_tariff: Mapped[str | None] = mapped_column(String, nullable=True)
    subscription_end: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    # new -> active -> grace -> paused
    status: Mapped[str] = mapped_column(String, default="new")

    last_inv_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_day_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    autopay_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    grace_started: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    tariff: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))

    # pending -> success / failed
    status: Mapped[str] = mapped_column(String, default="pending")
    is_recurring: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN email VARCHAR",
    "ALTER TABLE users ADD COLUMN getcourse_user_id BIGINT",
    "ALTER TABLE users ADD COLUMN last_day_reminder_sent BOOLEAN DEFAULT 0",
    "ALTER TABLE users ADD COLUMN autopay_attempted BOOLEAN DEFAULT 0",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass


# ============ ПОЛЬЗОВАТЕЛИ ============

async def get_or_create_user(telegram_id: int, username: str | None, full_name: str | None) -> User:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        elif username or full_name:
            if username:
                user.username = username
            if full_name:
                user.full_name = full_name
            await session.commit()
        return user


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        return await session.get(User, telegram_id)


async def set_user_email(telegram_id: int, email: str) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.email = email.strip().lower()
            await session.commit()


async def set_getcourse_user_id(telegram_id: int, gc_user_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.getcourse_user_id = gc_user_id
            await session.commit()


async def get_all_users(offset: int = 0, limit: int = 10) -> list[User]:
    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())


async def count_users() -> int:
    async with async_session() as session:
        result = await session.execute(select(User))
        return len(result.scalars().all())


async def count_active_by_tariff() -> dict[str, int]:
    async with async_session() as session:
        result = await session.execute(
            select(User.current_tariff).where(User.status == "active")
        )
        counts: dict[str, int] = {}
        for (tariff,) in result.all():
            if tariff:
                counts[tariff] = counts.get(tariff, 0) + 1
        return counts


async def count_by_status() -> dict[str, int]:
    async with async_session() as session:
        result = await session.execute(select(User.status))
        counts: dict[str, int] = {}
        for (status,) in result.all():
            counts[status] = counts.get(status, 0) + 1
        return counts


# ============ ПЛАТЕЖИ ============

async def create_payment(telegram_id: int, tariff: str, amount: float, is_recurring: bool = False) -> int:
    async with async_session() as session:
        payment = Payment(
            telegram_id=telegram_id,
            tariff=tariff,
            amount=amount,
            is_recurring=is_recurring,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        logger.info("Создан платёж id=%s user=%s tariff=%s amount=%s", payment.id, telegram_id, tariff, amount)
        return payment.id


async def get_payment(payment_id: int) -> Payment | None:
    async with async_session() as session:
        return await session.get(Payment, payment_id)


async def mark_payment(payment_id: int, status: str) -> None:
    async with async_session() as session:
        await session.execute(
            update(Payment).where(Payment.id == payment_id).values(status=status)
        )
        await session.commit()
        logger.info("Платёж id=%s статус=%s", payment_id, status)


# ============ ПОДПИСКА ============

async def activate_subscription(telegram_id: int, tariff: str, inv_id: int) -> datetime.datetime:
    days = TARIFFS[tariff]["days"]

    async with async_session() as session:
        user = await session.get(User, telegram_id)
        now = datetime.datetime.utcnow()

        if user.subscription_end and user.subscription_end > now and user.status == "active":
            base_date = user.subscription_end
        else:
            base_date = now

        new_end = base_date + datetime.timedelta(days=days)

        user.current_tariff = tariff
        user.subscription_end = new_end
        user.status = "active"
        user.last_inv_id = inv_id
        user.reminder_sent = False
        user.last_day_reminder_sent = False
        user.autopay_attempted = False
        user.grace_started = None

        await session.commit()
        logger.info("Подписка активирована user=%s tariff=%s до=%s", telegram_id, tariff, new_end)
        return new_end


async def admin_extend_subscription(telegram_id: int, tariff: str) -> datetime.datetime | None:
    """Ручное продление администратором без платежа."""
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return None

        now = datetime.datetime.utcnow()
        days = TARIFFS[tariff]["days"]
        base = user.subscription_end if user.subscription_end and user.subscription_end > now else now
        new_end = base + datetime.timedelta(days=days)

        user.current_tariff = tariff
        user.subscription_end = new_end
        user.status = "active"
        user.reminder_sent = False
        user.last_day_reminder_sent = False
        user.autopay_attempted = False
        user.grace_started = None

        await session.commit()
        logger.info("Админ продлил user=%s tariff=%s до=%s", telegram_id, tariff, new_end)
        return new_end


async def set_status(telegram_id: int, status: str) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.status = status
            await session.commit()
            logger.info("Статус user=%s -> %s", telegram_id, status)


async def set_grace(telegram_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.status = "grace"
            user.grace_started = datetime.datetime.utcnow()
            await session.commit()
            logger.info("Grace period user=%s", telegram_id)


async def mark_reminder_sent(telegram_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.reminder_sent = True
            await session.commit()


async def mark_last_day_reminder_sent(telegram_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.last_day_reminder_sent = True
            await session.commit()


async def mark_autopay_attempted(telegram_id: int) -> None:
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.autopay_attempted = True
            await session.commit()


# ============ ЗАПРОСЫ ДЛЯ ПЛАНИРОВЩИКА ============

async def get_users_for_reminder(window_start: datetime.datetime, window_end: datetime.datetime) -> list[User]:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.status == "active",
                User.subscription_end >= window_start,
                User.subscription_end <= window_end,
                User.reminder_sent == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())


async def get_users_for_last_day_reminder(now: datetime.datetime) -> list[User]:
    """Подписка истекает сегодня — последнее напоминание."""
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + datetime.timedelta(days=1)

    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.status == "active",
                User.subscription_end >= day_start,
                User.subscription_end < day_end,
                User.reminder_sent == True,  # noqa: E712
                User.last_day_reminder_sent == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())


async def get_users_for_autopay(now: datetime.datetime) -> list[User]:
    """
    Сценарий Б: подписка истекла, напоминание за 3 дня было отправлено,
    пользователь не выбрал тариф — пробуем автосписание по текущему тарифу.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.status == "active",
                User.subscription_end < now,
                User.reminder_sent == True,  # noqa: E712
                User.autopay_attempted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())


async def get_grace_expired_users(deadline: datetime.datetime) -> list[User]:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.status == "grace",
                User.grace_started < deadline,
            )
        )
        return list(result.scalars().all())
