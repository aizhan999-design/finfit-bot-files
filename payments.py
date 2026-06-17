import hashlib
import json
from urllib.parse import urlencode, quote

from config import (
    ROBOKASSA_LOGIN,
    ROBOKASSA_PASSWORD1,
    ROBOKASSA_PASSWORD2,
    ROBOKASSA_TEST_PASSWORD1,
    ROBOKASSA_TEST_PASSWORD2,
    ROBOKASSA_IS_TEST,
    ROBOKASSA_TAX,
    ROBOKASSA_RECURRING_ENABLED,
    ROBOKASSA_USE_RECEIPT,
    ROBOKASSA_SUCCESS_URL,
    ROBOKASSA_FAIL_URL,
)

ROBOKASSA_PAY_URL = "https://auth.robokassa.kz/Merchant/Index.aspx"
ROBOKASSA_RECURRING_URL = "https://auth.robokassa.kz/Merchant/Recurring"


def _is_test_mode() -> bool:
    return ROBOKASSA_IS_TEST == "1"


def _password1() -> str:
    if _is_test_mode() and ROBOKASSA_TEST_PASSWORD1:
        return ROBOKASSA_TEST_PASSWORD1
    return ROBOKASSA_PASSWORD1


def _password2() -> str:
    if _is_test_mode() and ROBOKASSA_TEST_PASSWORD2:
        return ROBOKASSA_TEST_PASSWORD2
    return ROBOKASSA_PASSWORD2


def _format_amount(amount: float) -> str:
    return f"{amount:.2f}"


def _build_receipt(amount: float, description: str) -> str:
    receipt = {
        "items": [
            {
                "name": description[:128],
                "quantity": 1,
                "sum": amount,
                "tax": ROBOKASSA_TAX,
            }
        ],
    }
    return json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def _payment_signature(out_sum: str, inv_id: int, receipt: str | None) -> str:
    pwd = _password1()
    if receipt and ROBOKASSA_USE_RECEIPT:
        receipt_for_sig = quote(receipt, safe="")
        signature_base = f"{ROBOKASSA_LOGIN}:{out_sum}:{inv_id}:{receipt_for_sig}:{pwd}"
    else:
        signature_base = f"{ROBOKASSA_LOGIN}:{out_sum}:{inv_id}:{pwd}"
    return hashlib.md5(signature_base.encode()).hexdigest()


def generate_payment_link(inv_id: int, amount: float, description: str, is_recurring_first: bool = False) -> str:
    out_sum = _format_amount(amount)
    receipt = _build_receipt(amount, description) if ROBOKASSA_USE_RECEIPT else None
    signature = _payment_signature(out_sum, inv_id, receipt)

    params = {
        "MerchantLogin": ROBOKASSA_LOGIN,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": description,
        "SignatureValue": signature,
        "Culture": "ru",
        "Encoding": "utf-8",
        "SuccessURL": ROBOKASSA_SUCCESS_URL,
        "FailURL": ROBOKASSA_FAIL_URL,
    }
    if receipt:
        params["Receipt"] = receipt
    if _is_test_mode():
        params["IsTest"] = 1
    if is_recurring_first and ROBOKASSA_RECURRING_ENABLED:
        params["Recurring"] = "true"

    return f"{ROBOKASSA_PAY_URL}?{urlencode(params)}"


def check_result_signature(out_sum: str, inv_id: str, signature: str) -> bool:
    expected_base = f"{out_sum}:{inv_id}:{_password2()}"
    expected = hashlib.md5(expected_base.encode()).hexdigest()
    return expected.lower() == signature.lower()


async def charge_recurring(session, new_inv_id: int, previous_inv_id: int, amount: float, description: str) -> bool:
    if not ROBOKASSA_RECURRING_ENABLED:
        return False

    out_sum = _format_amount(amount)
    receipt = _build_receipt(amount, description) if ROBOKASSA_USE_RECEIPT else None
    pwd = _password1()

    if receipt and ROBOKASSA_USE_RECEIPT:
        receipt_for_sig = quote(receipt, safe="")
        signature_base = f"{ROBOKASSA_LOGIN}:{out_sum}:{new_inv_id}:{receipt_for_sig}:{pwd}"
    else:
        signature_base = f"{ROBOKASSA_LOGIN}:{out_sum}:{new_inv_id}:{pwd}"
    signature = hashlib.md5(signature_base.encode()).hexdigest()

    params = {
        "MerchantLogin": ROBOKASSA_LOGIN,
        "InvoiceID": new_inv_id,
        "PreviousInvoiceID": previous_inv_id,
        "Signature": signature,
        "OutSum": out_sum,
    }
    if receipt:
        params["Receipt"] = receipt

    async with session.get(ROBOKASSA_RECURRING_URL, params=params) as resp:
        text = await resp.text()
        return resp.status == 200 and "error" not in text.lower()
