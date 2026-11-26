from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("users/", views.users_list, name="users_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("org/", views.org_structure, name="org_structure"),
    path("org/tree/", views.org_tree, name="org_tree"),
    path("org/departments/<int:pk>/info/", views.department_info, name="department_info"),
    path("org/users/<int:pk>/info/", views.user_info, name="user_info"),
    path("org/unassigned/", views.unassigned_info, name="unassigned_info"),
    path("counterparty/", views.counterparty_check, name="counterparty_check"),
]

handler404 = "core.views.page_not_found"
