import json
from datetime import datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from .forms import (
    CounterpartyCheckForm,
    LoginForm,
    PasswordChangeForm,
    ProfileForm,
    UserForm,
)
from .models import (
    ROLE_ADMIN,
    Counterparty,
    Department,
    HistoryCheckCounterparty,
    Role,
    User,
)
from .services.counterparty import (
    SOURCE_NAME,
    CounterpartyServiceError,
    run_counterparty_check,
)

CACHE_PERIOD = timedelta(days=30)


def admin_required(view_func):
    """Доступ только для авторизованных администраторов."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin:
            return render(request, "403.html", status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped


# ---------------------------------------------------------------------------
# Авторизация
# ---------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login_value = form.cleaned_data["login"].strip()
        password = form.cleaned_data["password"]
        candidate = User.objects.filter(login__iexact=login_value).first()

        if candidate and not candidate.active:
            form.add_error(
                None,
                "Учётная запись деактивирована. Обратитесь к администратору.",
            )
        else:
            user = authenticate(
                request,
                username=candidate.login if candidate else login_value,
                password=password,
            )
            if user is None:
                form.add_error(None, "Неверный логин или пароль.")
            else:
                login(request, user)
                messages.success(request, f"Добро пожаловать, {user.name}!")
                next_url = request.POST.get("next") or request.GET.get("next")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect("home")

    return render(
        request,
        "login.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
    )


def logout_view(request):
    logout(request)
    messages.info(request, "Вы вышли из системы.")
    return redirect("login")


# ---------------------------------------------------------------------------
# Главная и личный кабинет
# ---------------------------------------------------------------------------
@login_required
def home(request):
    stats = {
        "users": User.objects.count(),
        "departments": Department.objects.count(),
        "counterparties": Counterparty.objects.count(),
        "checks": HistoryCheckCounterparty.objects.successful().count(),
    }
    recent_checks = HistoryCheckCounterparty.objects.successful().select_related(
        "counterparty", "user"
    )[:6]
    my_checks = HistoryCheckCounterparty.objects.successful().select_related(
        "counterparty"
    ).filter(user=request.user)[:4]
    top_departments = (
        Department.objects.filter(parent__isnull=True)
        .prefetch_related("children")
        .order_by("id")
    )
    return render(
        request,
        "home.html",
        {
            "stats": stats,
            "recent_checks": recent_checks,
            "my_checks": my_checks,
            "top_departments": top_departments,
        },
    )


@login_required
def profile(request):
    form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Личные данные обновлены.")
                return redirect("profile")
        elif action == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data["new_password"])
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Пароль изменён. Соль перегенерирована.")
                return redirect("profile")

    return render(
        request,
        "profile.html",
        {
            "form": form,
            "password_form": password_form,
        },
    )


# ---------------------------------------------------------------------------
# Пользователи (только администратор)
# ---------------------------------------------------------------------------
@admin_required
def users_list(request):
    users = User.objects.select_related("role", "department").order_by("name")
    query = (request.GET.get("q") or "").strip()
    role_id = (request.GET.get("role") or "").strip()
    department_id = (request.GET.get("department") or "").strip()
    active = (request.GET.get("active") or "").strip()

    if query:
        users = users.filter(Q(name__icontains=query) | Q(login__icontains=query))
    if role_id.isdigit():
        users = users.filter(role_id=role_id)
    if department_id.isdigit():
        users = users.filter(department_id=department_id)
    if active in ("0", "1"):
        users = users.filter(active=active == "1")

    paginator = Paginator(users, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "total": paginator.count,
        "roles": Role.objects.all(),
        "departments": Department.objects.order_by("id"),
        "filters": {
            "q": query,
            "role": role_id,
            "department": department_id,
            "active": active,
        },
    }
    return render(request, "users/list.html", context)


@admin_required
def user_create(request):
    form = UserForm(request.POST or None, is_create=True)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Пользователь «{user.name}» создан.")
        return redirect("users_list")
    return render(
        request,
        "users/form.html",
        {"form": form, "mode": "create", "user_obj": None},
    )


@admin_required
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=user_obj)

    if request.method == "POST" and form.is_valid():
        if user_obj.pk == request.user.pk:
            if not form.cleaned_data.get("active"):
                form.add_error("active", "Нельзя деактивировать собственную учётную запись.")
            role = form.cleaned_data.get("role")
            if role and role.name != ROLE_ADMIN:
                form.add_error("role", "Нельзя снять с себя роль администратора.")
        if not form.errors:
            form.save()
            messages.success(request, f"Данные пользователя «{user_obj.name}» сохранены.")
            return redirect("users_list")

    return render(
        request,
        "users/form.html",
        {"form": form, "mode": "edit", "user_obj": user_obj},
    )


# ---------------------------------------------------------------------------
# Орг структура
# ---------------------------------------------------------------------------
@login_required
def org_structure(request):
    return render(
        request,
        "org.html",
        {
            "department_count": Department.objects.count(),
            "user_count": User.objects.count(),
        },
    )


def _user_node(user):
    return {
        "id": f"user_{user.pk}",
        "text": user.name,
        "type": "user",
        "children": False,
    }


def _department_node(department):
    has_children = department.children.exists()
    if not has_children:
        has_children = User.objects.filter(department=department).exists()
    if not has_children and department.boss_id:
        has_children = True
    return {
        "id": f"dept_{department.pk}",
        "text": department.name,
        "type": "department",
        "children": has_children,
    }


@login_required
@require_GET
def org_tree(request):
    node_id = request.GET.get("id", "#")

    if node_id in ("#", "", "root"):
        nodes = [
            _department_node(department)
            for department in Department.objects.filter(parent__isnull=True).order_by("id")
        ]
        if User.objects.filter(department__isnull=True).exists():
            nodes.append(
                {
                    "id": "dept_none",
                    "text": "Без департамента",
                    "type": "group",
                    "children": True,
                }
            )
        return JsonResponse(nodes, safe=False)

    if node_id == "dept_none":
        users = User.objects.filter(department__isnull=True).order_by("name")
        return JsonResponse([_user_node(user) for user in users], safe=False)

    if node_id.startswith("dept_"):
        department_id = node_id.removeprefix("dept_")
        if not department_id.isdigit():
            return JsonResponse([], safe=False)
        department = get_object_or_404(Department, pk=int(department_id))
        nodes = [
            _department_node(child)
            for child in department.children.order_by("id")
        ]
        employees = list(
            department.employees.select_related("role").order_by("name")
        )
        if department.boss_id and all(user.pk != department.boss_id for user in employees):
            employees.insert(0, department.boss)
        nodes.extend(_user_node(user) for user in employees)
        return JsonResponse(nodes, safe=False)

    return JsonResponse([], safe=False)


def _user_brief(user):
    if user is None:
        return None
    return {
        "id": user.pk,
        "name": user.name,
        "login": user.login,
        "initials": user.initials,
        "role": user.role_name,
        "department": user.department_name,
        "active": user.active,
        "is_admin": user.is_admin,
    }


@login_required
@require_GET
def department_info(request, pk):
    department = get_object_or_404(
        Department.objects.select_related("boss__role", "boss__department", "parent"),
        pk=pk,
    )
    subtree_ids = department.get_descendant_ids()
    subtree = Department.objects.filter(pk__in=subtree_ids)

    employee_ids = set(
        User.objects.filter(department_id__in=subtree_ids).values_list("id", flat=True)
    )
    employee_ids.update(
        subtree.exclude(boss__isnull=True).values_list("boss_id", flat=True)
    )

    direct_employees = list(
        department.employees.select_related("role").order_by("name")
    )
    if department.boss_id and all(
        employee.pk != department.boss_id for employee in direct_employees
    ):
        direct_employees.insert(0, department.boss)

    return JsonResponse(
        {
            "kind": "department",
            "id": department.pk,
            "name": department.name,
            "parent_path": department.get_path(),
            "boss": _user_brief(department.boss),
            "subdepartment_count": len(subtree_ids) - 1,
            "employee_count": len(employee_ids),
            "direct_employee_count": User.objects.filter(department=department).count(),
            "direct_employees": [_user_brief(user) for user in direct_employees[:12]],
        }
    )


@login_required
@require_GET
def user_info(request, pk):
    user = get_object_or_404(
        User.objects.select_related("role", "department"), pk=pk
    )
    headed = list(user.headed_departments.order_by("id").values_list("name", flat=True))
    return JsonResponse(
        {
            "kind": "user",
            **_user_brief(user),
            "headed_departments": headed,
            "checks_count": user.counterparty_checks.successful().count(),
        }
    )


@login_required
@require_GET
def unassigned_info(request):
    users = list(
        User.objects.filter(department__isnull=True)
        .select_related("role")
        .order_by("name")
    )
    return JsonResponse(
        {
            "kind": "group",
            "name": "Без департамента",
            "employee_count": len(users),
            "employees": [_user_brief(user) for user in users],
        }
    )


# ---------------------------------------------------------------------------
# Проверка контрагентов
# ---------------------------------------------------------------------------
@login_required
def counterparty_check(request):
    form = CounterpartyCheckForm(request.POST or None)
    context = {
        "form": form,
        "history": HistoryCheckCounterparty.objects.successful().select_related(
            "counterparty", "user"
        )[:6],
        "history_title": "Последние проверки в компании",
        "result": None,
        "counterparty": None,
        "cached": False,
        "error": False,
    }

    if request.method == "POST" and form.is_valid():
        inn = form.cleaned_data["inn"]
        counterparty = Counterparty.objects.filter(inn=inn).first()
        latest = (
            counterparty.checks.successful().select_related("user").first()
            if counterparty
            else None
        )
        now = timezone.now()
        # Кэшем считаются только результаты реальной интеграции: старые
        # демо-записи (source = "demo") не используются.
        cached = bool(
            latest
            and now - latest.date_time < CACHE_PERIOD
            and latest.result_data.get("source") == SOURCE_NAME
        )
        created = False

        if cached:
            result = dict(latest.result_data)
            if result.get("registration_date") and not result.get("registration_date_display"):
                try:
                    result["registration_date_display"] = datetime.strptime(
                        result["registration_date"], "%Y-%m-%d"
                    ).strftime("%d.%m.%Y")
                except (TypeError, ValueError):
                    pass
            checked_at = latest.date_time
            checked_by = latest.user
            cache_until = latest.date_time + CACHE_PERIOD
        else:
            try:
                result = run_counterparty_check(inn)
            except CounterpartyServiceError as exc:
                # Текст ошибки сохраняем в БД, пользователю он не показывается.
                if counterparty is None:
                    counterparty = Counterparty.objects.create(inn=inn, name=f"ИНН {inn}")
                HistoryCheckCounterparty.objects.create(
                    counterparty=counterparty,
                    user=request.user,
                    result="",
                    error_text=exc.detail[:2000],
                )
                context["error"] = True
                return render(request, "counterparty.html", context)

            if counterparty is None:
                counterparty = Counterparty.objects.create(inn=inn, name=result["name"])
                created = True
            elif counterparty.name != result["name"]:
                counterparty.name = result["name"]
                counterparty.save(update_fields=["name"])
            history_record = HistoryCheckCounterparty.objects.create(
                counterparty=counterparty,
                user=request.user,
                result=json.dumps(result, ensure_ascii=False),
            )
            checked_at = history_record.date_time
            checked_by = request.user
            cache_until = history_record.date_time + CACHE_PERIOD

        context.update(
            {
                "result": result,
                "counterparty": counterparty,
                "cached": cached,
                "checked_at": checked_at,
                "checked_by": checked_by,
                "cache_until": cache_until,
                "history": counterparty.checks.successful().select_related("user")[:6],
                "history_title": "Последние 6 проверок этой компании",
            }
        )
        if created:
            messages.info(
                request,
                f"Контрагент «{counterparty.name}» добавлен в справочник.",
            )

    return render(request, "counterparty.html", context)


def page_not_found(request, exception):
    return render(request, "404.html", status=404)
