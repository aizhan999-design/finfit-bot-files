import base64
import json
import logging
from typing import Any

from aiohttp import ClientSession

from config import GETCOURSE_ACCOUNT, GETCOURSE_API_KEY, GETCOURSE_GROUP_NAME

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(GETCOURSE_ACCOUNT and GETCOURSE_API_KEY and GETCOURSE_GROUP_NAME)


def _api_url() -> str:
    return f"https://{GETCOURSE_ACCOUNT}.getcourse.ru/pl/api/users"


def _encode_params(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()


def _extract_user_id(result: dict) -> int | None:
    uid = result.get("result", {}).get("user_id")
    if uid:
        try:
            return int(uid)
        except (TypeError, ValueError):
            return None
    return None


async def _call_api(session: ClientSession, action: str, params: dict[str, Any]) -> dict:
    if not is_configured():
        logger.warning("GetCourse не настроен, пропускаем API-вызов: %s", action)
        return {"success": False, "skipped": True}

    payload = {
        "action": action,
        "key": GETCOURSE_API_KEY,
        "params": _encode_params(params),
    }

    try:
        async with session.post(_api_url(), data=payload) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                logger.error("GetCourse: неверный JSON (%s): %s", action, text[:300])
                return {"success": False, "error": text}

            if result.get("success"):
                logger.info("GetCourse %s OK: %s", action, params.get("user", {}).get("email"))
            else:
                logger.error("GetCourse %s ошибка: %s", action, result)
            return result
    except Exception as exc:
        logger.exception("GetCourse %s исключение: %s", action, exc)
        return {"success": False, "error": str(exc)}


def _user_payload(
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    groups: list[str] | None = None,
) -> dict[str, Any]:
    user: dict[str, Any] = {"email": email}
    if first_name:
        user["first_name"] = first_name
    if last_name:
        user["last_name"] = last_name
    if groups is not None:
        user["group_name"] = groups
    return {"user": user, "system": {"refresh_if_exists": 1}}


async def _resolve_user_id(session: ClientSession, email: str) -> int | None:
    """Получает user_id существующего пользователя через action=add."""
    params = {"user": {"email": email}, "system": {"refresh_if_exists": 1}}
    result = await _call_api(session, "add", params)
    return _extract_user_id(result)


async def grant_access(
    session: ClientSession,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> int | None:
    params = _user_payload(
        email, first_name, last_name, groups=[GETCOURSE_GROUP_NAME]
    )
    result = await _call_api(session, "add", params)
    if result.get("success") or result.get("skipped"):
        return _extract_user_id(result)
    return None


async def revoke_access(
    session: ClientSession,
    email: str,
    user_id: int | None = None,
) -> bool:
    gc_id = user_id
    if not gc_id:
        gc_id = await _resolve_user_id(session, email)
    if not gc_id:
        logger.warning("GetCourse revoke: не найден user_id для %s", email)
        return False

    params = {"user": {"id": str(gc_id), "group_name": []}}
    result = await _call_api(session, "update", params)
    return result.get("success", False) or result.get("skipped", False)


async def restore_access(
    session: ClientSession,
    email: str,
    first_name: str | None = None,
) -> int | None:
    return await grant_access(session, email, first_name)
