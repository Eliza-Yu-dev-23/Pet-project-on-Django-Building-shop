"""Быстрый smoke-тест основных сценариев (запускается внутри контейнера)."""
import json
import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import Counterparty, Department, HistoryCheckCounterparty, User

settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

checks = []


def check(name, condition, detail=""):
    checks.append((name, bool(condition), detail))
    print(("OK   " if condition else "FAIL ") + name + (f" — {detail}" if detail else ""))


admin = User.objects.get(login="admin")
root = Department.objects.get(name="Руководство")
sales = Department.objects.get(name="Отдел продаж")
employee = User.objects.get(login="employee")

check("static salt заполнен", bool(admin.hash), admin.hash[:8])
check("пароль в формате соли", admin.password.startswith("pbkdf2_sha256$"))
check("проверка пароля admin", admin.check_password("Admin#2026"))
check("неверный пароль отклонён", not admin.check_password("wrong"))
check("17 пользователей", User.objects.count() == 17, str(User.objects.count()))
check("6 департаментов", Department.objects.count() == 6)
check("иерархия продаж", sales.parent_id == root.pk)
check("у руководителя есть начальник", root.boss_id == admin.pk)

client = Client()
response = client.post(
    reverse("login"), {"login": "admin", "password": "Admin#2026"}
)
check("вход администратора", response.status_code == 302, str(response.status_code))

for name, url in [
    ("главная", reverse("home")),
    ("орг структура", reverse("org_structure")),
    ("проверка контрагента", reverse("counterparty_check")),
    ("профиль", reverse("profile")),
    ("пользователи", reverse("users_list")),
]:
    response = client.get(url)
    check(f"GET {name}", response.status_code == 200, str(response.status_code))

response = client.get(reverse("users_list"), {"q": "Соколов", "role": admin.role_id})
check("поиск и фильтр пользователей", response.status_code == 200 and "Соколов" in response.content.decode())

tree = client.get(reverse("org_tree")).json()
check("корневой узел дерева", len(tree) == 1 and tree[0]["text"] == "Руководство", json.dumps(tree, ensure_ascii=False))

tree = client.get(reverse("org_tree"), {"id": f"dept_{sales.pk}"}).json()
names = [node["text"] for node in tree]
check(
    "ленивая загрузка детей и сотрудников",
    "Отдел строительных материалов" in names and "Сергей Волков" in names,
    ", ".join(names),
)

info = client.get(reverse("department_info", args=[root.pk])).json()
check("подчинённых департаментов 5", info["subdepartment_count"] == 5, str(info["subdepartment_count"]))
check("сотрудников в дереве 17", info["employee_count"] == 17, str(info["employee_count"]))

user_info = client.get(reverse("user_info", args=[employee.pk])).json()
check("панель пользователя", user_info["kind"] == "user" and user_info["login"] == "employee")

# Проверка контрагента: кэш, новая проверка, история.
cp = Counterparty.objects.get(inn="7707083893")
before = cp.checks.count()
response = client.post(reverse("counterparty_check"), {"inn": "7707083893"})
check("кэш проверки < 30 дней", response.status_code == 200 and "Использован кэш" in response.content.decode())
check("история не выросла при кэше", cp.checks.count() == before, str(cp.checks.count()))

new_inn = "7707329152"
Counterparty.objects.filter(inn=new_inn).delete()
response = client.post(reverse("counterparty_check"), {"inn": new_inn})
check("новая проверка по ИНН", response.status_code == 200 and "Выполнена новая проверка" in response.content.decode())
check("создан контрагент", Counterparty.objects.filter(inn=new_inn).exists())
new_cp = Counterparty.objects.get(inn=new_inn)
check("создана запись истории", new_cp.checks.count() == 1)
check("история от текущего пользователя", new_cp.checks.first().user_id == admin.pk)

response = client.post(reverse("counterparty_check"), {"inn": new_inn})
check("повторная проверка из кэша", "Использован кэш" in response.content.decode())
check("записей всё ещё 1", new_cp.checks.count() == 1)

response = client.post(reverse("counterparty_check"), {"inn": "1234567890"})
check("некорректный ИНН отклонён", "контрольной суммы" in response.content.decode())

# Доступ сотрудника.
client2 = Client()
client2.post(reverse("login"), {"login": "employee", "password": "Employee#2026"})
response = client2.get(reverse("users_list"))
check("сотруднику закрыт раздел пользователей", response.status_code == 403, str(response.status_code))

# Неактивный пользователь.
inactive = User(login="inactive.demo", name="Неактивный Демо", active=False)
inactive.set_password("Inactive#2026")
inactive.save()
client3 = Client()
response = client3.post(
    reverse("login"), {"login": "inactive.demo", "password": "Inactive#2026"}
)
check(
    "неактивный пользователь не пускается",
    response.status_code == 200 and "деактивирована" in response.content.decode(),
)
inactive.delete()

failed = [name for name, ok, _ in checks if not ok]
print()
print(f"Итого: {len(checks) - len(failed)}/{len(checks)} успешно")
if failed:
    print("Провалено:", ", ".join(failed))
    raise SystemExit(1)
