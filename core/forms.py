from django import forms

from .models import Department, Role, User
from .services.counterparty import validate_inn


class LoginForm(forms.Form):
    login = forms.CharField(
        label="Логин",
        widget=forms.TextInput(
            attrs={
                "class": "uk-input uk-form-large",
                "placeholder": "Введите логин",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "uk-input uk-form-large",
                "placeholder": "Введите пароль",
                "autocomplete": "current-password",
            }
        ),
    )


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label="Пароль",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "uk-input",
                "autocomplete": "new-password",
                "placeholder": "Минимум 8 символов",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["login", "name", "role", "department", "active"]
        widgets = {
            "login": forms.TextInput(
                attrs={"class": "uk-input", "placeholder": "Например, i.ivanov"}
            ),
            "name": forms.TextInput(
                attrs={"class": "uk-input", "placeholder": "Фамилия Имя Отчество"}
            ),
            "role": forms.Select(attrs={"class": "uk-select"}),
            "department": forms.Select(attrs={"class": "uk-select"}),
            "active": forms.CheckboxInput(attrs={"class": "uk-checkbox"}),
        }

    def __init__(self, *args, is_create=False, **kwargs):
        self.is_create = is_create
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.all()
        self.fields["role"].empty_label = "— выберите роль —"
        self.fields["department"].queryset = Department.objects.order_by("id")
        self.fields["department"].empty_label = "— без департамента —"
        self.fields["department"].required = False
        self.fields["role"].required = True

        if is_create:
            self.fields["password"].required = True
            self.fields["password"].help_text = (
                "Пароль будет сохранён как PBKDF2-хеш с динамической солью; "
                "статическая соль автоматически попадёт в колонку hash."
            )
        else:
            self.fields["password"].help_text = (
                "Оставьте поле пустым, чтобы сохранить текущий пароль."
            )

    def clean_login(self):
        login = (self.cleaned_data.get("login") or "").strip()
        if not login:
            raise forms.ValidationError("Логин обязателен.")
        if " " in login:
            raise forms.ValidationError("Логин не должен содержать пробелы.")
        return login

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Имя обязательно.")
        return name

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password and len(password) < 8:
            raise forms.ValidationError("Пароль должен содержать минимум 8 символов.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name", "department"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "uk-input"}),
            "department": forms.Select(attrs={"class": "uk-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.order_by("id")
        self.fields["department"].empty_label = "— без департамента —"
        self.fields["department"].required = False

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Имя обязательно.")
        return name


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Текущий пароль",
        widget=forms.PasswordInput(
            attrs={"class": "uk-input", "autocomplete": "current-password"}
        ),
    )
    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(
            attrs={"class": "uk-input", "autocomplete": "new-password"}
        ),
    )
    confirm_password = forms.CharField(
        label="Повторите новый пароль",
        widget=forms.PasswordInput(
            attrs={"class": "uk-input", "autocomplete": "new-password"}
        ),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password")
        if not self.user.check_password(password):
            raise forms.ValidationError("Текущий пароль указан неверно.")
        return password

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password and len(password) < 8:
            raise forms.ValidationError("Пароль должен содержать минимум 8 символов.")
        return password

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get("new_password")
        confirm_password = cleaned.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", "Пароли не совпадают.")
        return cleaned


class CounterpartyCheckForm(forms.Form):
    inn = forms.CharField(
        label="ИНН",
        max_length=12,
        widget=forms.TextInput(
            attrs={
                "class": "uk-input uk-form-large",
                "placeholder": "Например, 7707083893",
                "inputmode": "numeric",
                "autocomplete": "off",
                "maxlength": "12",
            }
        ),
    )

    def clean_inn(self):
        inn = (self.cleaned_data.get("inn") or "").strip().replace(" ", "")
        if not inn.isdigit():
            raise forms.ValidationError("ИНН должен состоять только из цифр.")
        if len(inn) not in (10, 12):
            raise forms.ValidationError("ИНН юридического лица — 10 цифр, ИП — 12 цифр.")
        if not validate_inn(inn):
            raise forms.ValidationError(
                "ИНН не прошёл проверку контрольной суммы. "
                "Для демонстрации подойдёт, например, 7707083893."
            )
        return inn
