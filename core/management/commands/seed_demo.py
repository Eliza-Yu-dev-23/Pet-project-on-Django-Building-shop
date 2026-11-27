"""Наполнение демонстрационной базы данными.

Команда идемпотентна: повторный запуск не создаёт дубликатов.
Флаг ``--reset`` полностью очищает данные портала перед заполнением.
"""
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    Counterparty,
    Department,
    HistoryCheckCounterparty,
    Role,
    User,
)
from core.services.demo_data import build_demo_result

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "Admin#2026"
EMPLOYEE_LOGIN = "employee"
EMPLOYEE_PASSWORD = "Employee#2026"

DEPARTMENT_TREE = [
    ("Руководство", None),
    ("Финансовый отдел", "Руководство"),
    ("Отдел продаж", "Руководство"),
    ("Склад и логистика", "Руководство"),
    ("Отдел строительных материалов", "Отдел продаж"),
    ("Отдел инструментов", "Отдел продаж"),
]

RANDOM_USERS = [
    ("d.sokolov", "Дмитрий Соколов", "Финансовый отдел", True),
    ("e.morozova", "Елена Морозова", "Финансовый отдел", False),
    ("s.volkov", "Сергей Волков", "Отдел продаж", True),
    ("a.kuznetsova", "Анна Кузнецова", "Отдел продаж", False),
    ("p.lebedev", "Павел Лебедев", "Склад и логистика", True),
    ("o.novikova", "Ольга Новикова", "Склад и логистика", False),
    ("i.smirnov", "Игорь Смирнов", "Отдел строительных материалов", True),
    ("m.popova", "Мария Попова", "Отдел строительных материалов", False),
    ("a.vasiliev", "Алексей Васильев", "Отдел инструментов", True),
    ("t.pavlova", "Татьяна Павлова", "Отдел инструментов", False),
    ("n.kozlov", "Николай Козлов", "Руководство", False),
    ("v.semenova", "Виктория Семёнова", "Отдел продаж", False),
    ("a.egorov", "Андрей Егоров", "Склад и логистика", False),
    ("y.orlova", "Юлия Орлова", "Финансовый отдел", False),
    ("m.nikitin", "Максим Никитин", "Отдел инструментов", False),
]

BOSS_BY_DEPARTMENT = {
    "Руководство": ADMIN_LOGIN,
    "Финансовый отдел": "d.sokolov",
    "Отдел продаж": "s.volkov",
    "Склад и логистика": "p.lebedev",
    "Отдел строительных материалов": "i.smirnov",
    "Отдел инструментов": "a.vasiliev",
}

COUNTERPARTIES = [
    ("7707083893", "ООО «СтройТрест»", [5, 45, 90]),
    ("7736207543", "ООО «МастерБетон»", [47, 120]),
    ("7728168971", "ООО «ИнструментПро»", [12, 210]),
    ("7702070139", "ООО «ГлавСнаб»", [80]),
]


class Command(BaseCommand):
    help = "Заполняет портал демо-данными (роли, департаменты, пользователи, контрагенты)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Удалить существующие данные портала перед заполнением",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Очистка существующих данных...")
            HistoryCheckCounterparty.objects.all().delete()
            Counterparty.objects.all().delete()
            User.objects.all().delete()
            Department.objects.all().delete()
            Role.objects.all().delete()

        admin_role, _ = Role.objects.get_or_create(name=ROLE_ADMIN)
        employee_role, _ = Role.objects.get_or_create(name=ROLE_EMPLOYEE)

        departments = {}
        for name, parent_name in DEPARTMENT_TREE:
            parent = departments.get(parent_name) if parent_name else None
            department, _ = Department.objects.get_or_create(
                name=name,
                defaults={"parent": parent},
            )
            if parent and department.parent_id != parent.pk:
                department.parent = parent
                department.save(update_fields=["parent"])
            departments[name] = department

        credentials = []

        def ensure_user(login, name, role, department, password=None):
            existing = User.objects.filter(login=login).first()
            if existing:
                return existing, False
            raw_password = password or f"Demo-{secrets.token_hex(3)}!"
            user = User(
                login=login,
                name=name,
                role=role,
                department=department,
                active=True,
            )
            user.set_password(raw_password)
            user.save()
            credentials.append((login, raw_password, name, role.name))
            return user, True

        admin, _ = ensure_user(
            ADMIN_LOGIN,
            "Администратор Системы",
            admin_role,
            departments["Руководство"],
            ADMIN_PASSWORD,
        )
        employee, _ = ensure_user(
            EMPLOYEE_LOGIN,
            "Сотрудник Демо",
            employee_role,
            departments["Отдел продаж"],
            EMPLOYEE_PASSWORD,
        )

        for login, name, department_name, _is_boss in RANDOM_USERS:
            ensure_user(login, name, employee_role, departments[department_name])

        for department_name, login in BOSS_BY_DEPARTMENT.items():
            boss = User.objects.filter(login=login).first()
            if boss:
                Department.objects.filter(pk=departments[department_name].pk).update(boss=boss)

        # Демонстрационные контрагенты и история проверок.
        users = list(User.objects.all())
        for index, (inn, name, day_offsets) in enumerate(COUNTERPARTIES):
            counterparty, _ = Counterparty.objects.get_or_create(
                inn=inn, defaults={"name": name}
            )
            if counterparty.checks.exists():
                continue
            for offset in day_offsets:
                checked_at = timezone.now() - timedelta(
                    days=offset, hours=index * 2 + 1
                )
                result = build_demo_result(inn, counterparty.name, checked_at=checked_at)
                HistoryCheckCounterparty.objects.create(
                    counterparty=counterparty,
                    user=users[(offset + index) % len(users)],
                    date_time=checked_at,
                    result=json.dumps(result, ensure_ascii=False),
                )

        if credentials:
            path = settings.BASE_DIR / "demo_credentials.txt"
            lines = [
                "Демо-доступы портала «СтройБаза»",
                "=" * 42,
                "",
                "Администратор:",
                f"  логин:  {ADMIN_LOGIN}",
                f"  пароль: {ADMIN_PASSWORD}",
                "",
                "Сотрудник:",
                f"  логин:  {EMPLOYEE_LOGIN}",
                f"  пароль: {EMPLOYEE_PASSWORD}",
                "",
                "Остальные пользователи (сгенерированные пароли):",
            ]
            for login, password, name, role_name in credentials:
                lines.append(f"  {login:16} {password:18} {name} — {role_name}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Доступы сохранены в {path}"))

        self.stdout.write(
            self.style.SUCCESS(
                "Готово: "
                f"{Role.objects.count()} роли, "
                f"{Department.objects.count()} департаментов, "
                f"{User.objects.count()} пользователей, "
                f"{Counterparty.objects.count()} контрагентов, "
                f"{HistoryCheckCounterparty.objects.count()} записей истории."
            )
        )
        self.stdout.write(
            f"Администратор: {ADMIN_LOGIN} / {ADMIN_PASSWORD}\n"
            f"Сотрудник:     {EMPLOYEE_LOGIN} / {EMPLOYEE_PASSWORD}"
        )
