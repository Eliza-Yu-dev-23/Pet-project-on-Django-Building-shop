"""Модели корпоративного портала строительного магазина.

Схема БД повторяет приложенную ER-диаграмму:
Role, Department, User, Counterparty, HistoryCheckCounterparty.

Пароль пользователя хранится в виде PBKDF2-хеша с ДВУМЯ солями:
* статическая соль — персональное случайное значение в колонке ``User.hash``;
* динамическая соль — генерируется для каждого пароля и хранится рядом с хешем
  в колонке ``User.password`` в формате ``pbkdf2_sha256$<dynamic_salt>$<digest>``.
"""
import hashlib
import hmac
import json
import secrets

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

ROLE_ADMIN = "Администратор"
ROLE_EMPLOYEE = "Сотрудник"

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000


class Role(models.Model):
    name = models.CharField("Название", max_length=64, unique=True)

    class Meta:
        verbose_name = "Роль"
        verbose_name_plural = "Роли"
        ordering = ["id"]

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField("Название", max_length=255)
    parent = models.ForeignKey(
        "self",
        verbose_name="Родительский департамент",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    boss = models.ForeignKey(
        "User",
        verbose_name="Руководитель",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_departments",
    )

    class Meta:
        verbose_name = "Департамент"
        verbose_name_plural = "Департаменты"
        ordering = ["id"]

    def __str__(self):
        return self.name

    def get_descendant_ids(self):
        """ID департамента и всех его потомков (обход в ширину)."""
        ids = [self.pk]
        queue = [self]
        while queue:
            current = queue.pop(0)
            for child in current.children.all():
                ids.append(child.pk)
                queue.append(child)
        return ids

    def get_path(self):
        """Путь от корня до департамента: «Руководство / Отдел продаж»."""
        names = []
        node = self
        while node is not None:
            names.append(node.name)
            node = node.parent
        return " / ".join(reversed(names))


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, login, name, password=None, **extra_fields):
        if not login:
            raise ValueError("Логин обязателен")
        user = self.model(login=login, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login, name, password=None, **extra_fields):
        role, _ = Role.objects.get_or_create(name=ROLE_ADMIN)
        extra_fields.setdefault("role", role)
        extra_fields.setdefault("active", True)
        return self.create_user(login, name, password, **extra_fields)


class User(AbstractBaseUser):
    login = models.CharField("Логин", max_length=150, unique=True)
    name = models.CharField("Имя", max_length=255)
    password = models.CharField("Пароль (хеш)", max_length=255)
    department = models.ForeignKey(
        Department,
        verbose_name="Департамент",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    active = models.BooleanField("Активен", default=True)
    hash = models.CharField(
        "Статическая соль",
        max_length=255,
        blank=True,
        default="",
        help_text="Персональная статическая соль, хранится в БД.",
    )
    role = models.ForeignKey(
        Role,
        verbose_name="Роль",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )

    objects = UserManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.login})"

    # --- пароли ---------------------------------------------------------
    def _ensure_static_salt(self):
        if not self.hash:
            self.hash = secrets.token_hex(16)
        return self.hash

    def set_password(self, raw_password):
        if raw_password is None:
            self.set_unusable_password()
            return
        static_salt = self._ensure_static_salt()
        dynamic_salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            f"{static_salt}:{dynamic_salt}".encode("utf-8"),
            PASSWORD_ITERATIONS,
        ).hex()
        self.password = f"{PASSWORD_ALGORITHM}${dynamic_salt}${digest}"

    def check_password(self, raw_password):
        if not raw_password or not self.password or not self.hash:
            return False
        try:
            algorithm, dynamic_salt, digest = self.password.split("$", 2)
        except ValueError:
            return False
        if algorithm != PASSWORD_ALGORITHM:
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            f"{self.hash}:{dynamic_salt}".encode("utf-8"),
            PASSWORD_ITERATIONS,
        ).hex()
        return hmac.compare_digest(calculated, digest)

    def set_unusable_password(self):
        self.password = f"!{secrets.token_hex(16)}"

    def has_usable_password(self):
        return bool(self.password) and not self.password.startswith("!")

    # --- права и представление -----------------------------------------
    @property
    def is_active(self):
        return self.active

    @property
    def is_admin(self):
        return bool(self.role_id and self.role.name == ROLE_ADMIN)

    @property
    def is_staff(self):
        return self.is_admin

    @property
    def is_superuser(self):
        return self.is_admin

    @property
    def role_name(self):
        return self.role.name if self.role_id else "Без роли"

    @property
    def department_name(self):
        return self.department.name if self.department_id else "Без департамента"

    @property
    def initials(self):
        parts = [part for part in self.name.split() if part]
        if not parts:
            return self.login[:2].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split()[0] if self.name else self.login


class Counterparty(models.Model):
    name = models.CharField("Название", max_length=255)
    inn = models.CharField("ИНН", max_length=12, unique=True)

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (ИНН {self.inn})"


class HistoryCheckCounterparty(models.Model):
    counterparty = models.ForeignKey(
        Counterparty,
        verbose_name="Контрагент",
        on_delete=models.CASCADE,
        related_name="checks",
    )
    user = models.ForeignKey(
        User,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="counterparty_checks",
    )
    date_time = models.DateTimeField("Дата и время", default=timezone.now)
    result = models.TextField("Результат проверки (JSON)")

    class Meta:
        verbose_name = "История проверки контрагента"
        verbose_name_plural = "История проверок контрагентов"
        ordering = ["-date_time", "-id"]

    def __str__(self):
        return f"{self.counterparty} — {self.date_time:%d.%m.%Y %H:%M}"

    @property
    def result_data(self):
        try:
            return json.loads(self.result)
        except (TypeError, ValueError):
            return {
                "status": "Нет данных",
                "status_class": "muted",
                "risk_score": 0,
                "source": "unknown",
            }
