from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class ActiveUserMiddleware:
    """Не даёт деактивированному пользователю остаться в системе.

    Даже если сессия уже была открыта, при следующем запросе неактивный
    пользователь будет разлогинен и отправлен на страницу входа.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.active:
            logout(request)
            messages.warning(
                request,
                "Учётная запись деактивирована. Доступ в систему закрыт.",
            )
            return redirect("login")
        return self.get_response(request)
