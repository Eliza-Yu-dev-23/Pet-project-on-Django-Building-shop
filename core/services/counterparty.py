"""Сервис проверки контрагентов на основе API Checko (api.checko.ru, v2).

Контур.Фокус для API платный и бесплатного тарифа не имеет, поэтому используется
Checko: бесплатный тариф даёт 100 запросов в сутки на все методы.

Одна проверка = 2 запроса: ``/v2/company`` (или ``/v2/entrepreneur`` для ИП) и
``/v2/legal-cases`` (количество арбитражных дел).

Любая проблема при работе с интеграцией превращается в
``CounterpartyServiceError``. Его ``detail`` — технический текст для БД
(колонка ``HistoryCheckCounterparty.error_text``), пользователю он не
показывается; ключ API в ``detail`` не попадает.
"""
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

SOURCE_NAME = "checko"

API_BASE = "https://api.checko.ru/v2"
REQUEST_TIMEOUT = 10  # секунд

STATUS_RELIABLE = "Надёжный"
STATUS_MEDIUM = "Средний риск"
STATUS_HIGH = "Высокий риск"

_STATUS_CLASS = {
    STATUS_RELIABLE: "success",
    STATUS_MEDIUM: "warning",
    STATUS_HIGH: "danger",
}


class CounterpartyServiceError(Exception):
    """Ошибка интеграции; ``detail`` сохраняется в БД и не показывается на сайте."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def validate_inn(inn: str) -> bool:
    """Проверка формата и контрольной суммы ИНН (10 или 12 цифр)."""
    if not inn or not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = [int(char) for char in inn]

    if len(inn) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        control = sum(d * w for d, w in zip(digits, weights)) % 11 % 10
        return control == digits[9]

    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    control_11 = sum(d * w for d, w in zip(digits, weights_11)) % 11 % 10
    control_12 = sum(d * w for d, w in zip(digits, weights_12)) % 11 % 10
    return control_11 == digits[10] and control_12 == digits[11]


# ---------------------------------------------------------------------------
# HTTP-клиент
# ---------------------------------------------------------------------------
def _api_key() -> str:
    key = os.getenv("CHECKO_API_KEY", "").strip()
    if not key:
        raise CounterpartyServiceError("Не задан CHECKO_API_KEY")
    return key


def _call(method: str, params: dict) -> dict:
    """GET-запрос к Checko. Возвращает ``data`` ответа или кидает ошибку."""
    query = urllib.parse.urlencode({"key": _api_key(), **params})
    url = f"{API_BASE}/{method}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise CounterpartyServiceError(f"{method}: HTTP {exc.code}") from None
    except (socket.timeout, TimeoutError):
        raise CounterpartyServiceError(f"{method}: превышено время ожидания") from None
    except urllib.error.URLError as exc:
        raise CounterpartyServiceError(f"{method}: сеть недоступна ({exc.reason})") from None
    except OSError as exc:
        raise CounterpartyServiceError(f"{method}: {type(exc).__name__}") from None

    try:
        payload = json.loads(body)
    except ValueError:
        raise CounterpartyServiceError(f"{method}: ответ не является JSON") from None
    if not isinstance(payload, dict):
        raise CounterpartyServiceError(f"{method}: неожиданный формат ответа")

    meta = payload.get("meta") or {}
    if meta.get("status") == "error":
        raise CounterpartyServiceError(
            f"{method}: {str(meta.get('message') or 'ошибка сервиса')[:300]}"
        )
    data = payload.get("data")
    if not data:
        raise CounterpartyServiceError(f"{method}: нет данных по ИНН {params.get('inn')}")
    return data


# ---------------------------------------------------------------------------
# Разбор ответа
# ---------------------------------------------------------------------------
def _dig(value, *path):
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _positive(value) -> bool:
    """Есть ли в значении (число / словарь / список) положительная сумма."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, dict):
        return any(_positive(item) for item in value.values())
    if isinstance(value, list):
        return any(_positive(item) for item in value)
    return False


def _tax_debts(data: dict):
    """True/False, если сервис отдаёт сведения о недоимке, иначе None."""
    taxes = data.get("Налоги")
    if not isinstance(taxes, dict):
        return None
    for key, value in taxes.items():
        lowered = str(key).lower()
        if "недоим" in lowered or "задолж" in lowered:
            return _positive(value)
    return None


def _status_flags(status_text: str):
    """(неактивна/ликвидируется, банкротство) по текстовому статусу ЕГРЮЛ."""
    text = (status_text or "").lower()
    if not text or "не находится" in text:
        return False, False
    bankrupt = "банкрот" in text
    inactive = any(mark in text for mark in ("ликвидац", "исключ", "прекращ"))
    return inactive, bankrupt


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _calc_risk(*, inactive, bankrupt, tax_debts, sanctions, arbitration, age_days):
    score = 0
    if inactive:
        score += 60
    if bankrupt:
        score += 40
    if sanctions:
        score += 50
    if tax_debts:
        score += 25
    score += min(arbitration, 10) * 3
    if age_days is not None:
        if age_days < 365:
            score += 15
        elif age_days < 3 * 365:
            score += 5
    return min(score, 100)


def build_result(inn: str, data: dict, arbitration_total: int) -> dict:
    """Приводит ответ Checko к словарю, который показывает страница проверки."""
    is_ip = len(inn) == 12

    if is_ip:
        name = f"ИП {data.get('ФИО') or inn}".strip()
        ogrn = data.get("ОГРНИП")
        director = data.get("ФИО")
    else:
        name = data.get("НаимСокр") or data.get("НаимПолн") or f"ИНН {inn}"
        ogrn = data.get("ОГРН")
        managers = data.get("Руковод")
        first = managers[0] if isinstance(managers, list) and managers else managers
        director = _dig(first, "ФИО")

    address = data.get("ЮрАдрес")
    legal_address = address.get("АдресРФ") if isinstance(address, dict) else address

    okved = data.get("ОКВЭД")
    okved_text = None
    if isinstance(okved, dict) and okved.get("Код"):
        okved_text = f"{okved['Код']} — {okved.get('Наим', '')}".rstrip(" —")

    registration = None
    raw_date = data.get("ДатаРег")
    if raw_date:
        try:
            registration = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            registration = None

    status_text = _dig(data, "Статус", "Наим") or ""
    inactive, bankrupt = _status_flags(status_text)
    tax_debts = _tax_debts(data)
    sanctions = bool(data["Санкции"]) if "Санкции" in data else None
    age_days = (date.today() - registration).days if registration else None

    risk_score = _calc_risk(
        inactive=inactive,
        bankrupt=bankrupt,
        tax_debts=tax_debts,
        sanctions=sanctions,
        arbitration=arbitration_total,
        age_days=age_days,
    )
    if risk_score < 30:
        status, risk_label = STATUS_RELIABLE, "низкий"
    elif risk_score < 65:
        status, risk_label = STATUS_MEDIUM, "умеренный"
    else:
        status, risk_label = STATUS_HIGH, "высокий"

    return {
        "name": name,
        "status": status,
        "status_class": _STATUS_CLASS[status],
        "risk_score": risk_score,
        "risk_label": risk_label,
        "ogrn": ogrn or "—",
        "registration_date": registration.isoformat() if registration else "",
        "registration_date_display": registration.strftime("%d.%m.%Y") if registration else "—",
        "director": director or "—",
        "legal_address": legal_address or "—",
        "okved": okved_text or "—",
        "employees": _to_int(data.get("СЧР")),
        "arbitration_cases": arbitration_total,
        "tax_debts": tax_debts,
        "sanctions": sanctions,
        "bankruptcy": bankrupt,
        "source": SOURCE_NAME,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "comment": "",
    }


def run_counterparty_check(inn: str) -> dict:
    """Проверяет контрагента через Checko.

    Кидает ``CounterpartyServiceError`` при любой проблеме с интеграцией.
    """
    try:
        method = "entrepreneur" if len(inn) == 12 else "company"
        data = _call(method, {"inn": inn})
        cases = _call("legal-cases", {"inn": inn, "role": "defendant", "limit": 1})
        total = _to_int(_dig(cases, "ЗапВсего")) or 0
        return build_result(inn, data, total)
    except CounterpartyServiceError:
        raise
    except Exception as exc:  # неожиданный формат данных и т.п.
        raise CounterpartyServiceError(f"Ошибка разбора ответа: {type(exc).__name__}: {exc}") from None
