"""Сервис проверки контрагентов.

Сейчас интеграция с внешним API отсутствует: результат генерируется
демонстрационно (``build_demo_result``). Точка подключения реального сервиса —
функция ``run_counterparty_check``. Варианты бесплатных интеграций описаны в
``docs/counterparty_services.md``.
"""
import hashlib
import random
from datetime import date, timedelta

from django.utils import timezone

STATUS_RELIABLE = "Надёжный"
STATUS_MEDIUM = "Средний риск"
STATUS_HIGH = "Высокий риск"

_STATUS_CLASS = {
    STATUS_RELIABLE: "success",
    STATUS_MEDIUM: "warning",
    STATUS_HIGH: "danger",
}

_COMPANY_PREFIXES = [
    "Строй",
    "Мастер",
    "Глав",
    "Пром",
    "Бетон",
    "Инструмент",
    "Строй-",
    "Торг",
]
_COMPANY_SUFFIXES = [
    "Трест",
    "Снаб",
    "Монтаж",
    "Бетон",
    "Профи",
    "Логистик",
    "Мастер",
    "Комплект",
]
_SURNAMES = [
    "Смирнов",
    "Иванов",
    "Кузнецов",
    "Соколов",
    "Попов",
    "Лебедев",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
]
_INITIALS = ["А. В.", "С. П.", "И. И.", "Д. А.", "М. С.", "Е. Н.", "П. О."]
_DIRECTORS = [
    "Смирнов Алексей Викторович",
    "Иванов Дмитрий Сергеевич",
    "Кузнецова Елена Павловна",
    "Соколов Игорь Анатольевич",
    "Морозова Ольга Ивановна",
    "Волков Сергей Николаевич",
    "Лебедев Павел Андреевич",
    "Новикова Мария Алексеевна",
]
_CITIES = [
    "г. Москва",
    "г. Санкт-Петербург",
    "г. Екатеринбург",
    "г. Новосибирск",
    "г. Казань",
    "г. Краснодар",
    "г. Нижний Новгород",
]
_STREETS = [
    "ул. Строителей",
    "ул. Промышленная",
    "пр-т Мира",
    "ул. Заводская",
    "ул. Мастеровая",
    "ул. Бетонная",
    "ул. Индустриальная",
]
_OKVED = [
    "46.73 — Торговля оптовая лесоматериалами, строительными материалами и санитарно-техническим оборудованием",
    "47.52 — Торговля розничная скобяными изделиями, лакокрасочными материалами и стеклом",
    "43.99 — Работы строительные специализированные прочие",
    "41.20 — Строительство жилых и нежилых зданий",
    "46.74 — Торговля оптовая скобяными изделиями и водопроводным оборудованием",
    "47.53 — Торговля розничная строительными материалами",
]


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


def generate_counterparty_name(inn: str) -> str:
    """Правдоподобное название компании, детерминированное по ИНН."""
    rnd = random.Random(int(hashlib.md5(inn.encode("utf-8")).hexdigest(), 16))
    if len(inn) == 12:
        return f"ИП {rnd.choice(_SURNAMES)} {rnd.choice(_INITIALS)}"
    return f"ООО «{rnd.choice(_COMPANY_PREFIXES)}{rnd.choice(_COMPANY_SUFFIXES)}»"


def _random_ogrn(inn: str, rnd: random.Random) -> str:
    if len(inn) == 12:
        return str(rnd.randint(3, 4)) + "".join(str(rnd.randint(0, 9)) for _ in range(14))
    return str(rnd.choice([1, 5])) + "".join(str(rnd.randint(0, 9)) for _ in range(12))


def build_demo_result(inn: str, name: str, checked_at=None) -> dict:
    """Демонстрационный результат проверки (заглушка вместо интеграции)."""
    rnd = random.Random()
    roll = rnd.random()
    if roll < 0.56:
        status = STATUS_RELIABLE
        risk_score = rnd.randint(4, 28)
    elif roll < 0.87:
        status = STATUS_MEDIUM
        risk_score = rnd.randint(32, 64)
    else:
        status = STATUS_HIGH
        risk_score = rnd.randint(68, 94)

    registration = date.today() - timedelta(days=rnd.randint(800, 7200))
    employees = rnd.randint(6, 240)
    arbitration = rnd.randint(0, 9) if status != STATUS_RELIABLE else rnd.randint(0, 2)
    tax_debts = status == STATUS_HIGH or (status == STATUS_MEDIUM and rnd.random() < 0.35)
    sanctions = status == STATUS_HIGH and rnd.random() < 0.3
    bankruptcy = status == STATUS_HIGH and rnd.random() < 0.2

    return {
        "status": status,
        "status_class": _STATUS_CLASS[status],
        "risk_score": risk_score,
        "risk_label": (
            "низкий" if risk_score < 30 else "умеренный" if risk_score < 65 else "высокий"
        ),
        "ogrn": _random_ogrn(inn, rnd),
        "registration_date": registration.isoformat(),
        "registration_date_display": registration.strftime("%d.%m.%Y"),
        "director": rnd.choice(_DIRECTORS),
        "legal_address": f"{rnd.choice(_CITIES)}, {rnd.choice(_STREETS)}, д. {rnd.randint(1, 120)}",
        "okved": rnd.choice(_OKVED),
        "employees": employees,
        "arbitration_cases": arbitration,
        "tax_debts": tax_debts,
        "sanctions": sanctions,
        "bankruptcy": bankruptcy,
        "source": "demo",
        "checked_at": (checked_at or timezone.now()).isoformat(),
        "comment": (
            "Демонстрационные данные. Реальная интеграция с сервисом проверки "
            "контрагентов пока не подключена."
        ),
    }


def run_counterparty_check(inn: str, name: str) -> dict:
    """Точка подключения внешнего сервиса проверки контрагентов.

    Чтобы подключить реальный сервис (DaData, ФНС «Прозрачный бизнес»,
    Checko и т.п.), достаточно заменить тело функции на HTTP-запрос и
    привести ответ к тому же словарю, который возвращает
    ``build_demo_result``.
    """
    return build_demo_result(inn, name)
