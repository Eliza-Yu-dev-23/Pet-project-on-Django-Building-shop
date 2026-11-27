"""Случайные демонстрационные данные — используются ТОЛЬКО командой ``seed_demo``.

Реальная проверка контрагентов (``core/services/counterparty.py``) эти данные
не использует.
"""
import hashlib
import random
from datetime import date, timedelta

from django.utils import timezone

from .counterparty import _STATUS_CLASS, STATUS_HIGH, STATUS_MEDIUM, STATUS_RELIABLE

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
        "comment": "",
    }
