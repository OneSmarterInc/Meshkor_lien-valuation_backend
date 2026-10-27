from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import admin_views as a
from .views import LoginView, LogoutView, MeView

urlpatterns = [
    path("login/", LoginView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", MeView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("password/", a.ChangePassword.as_view()),
]

admin_urlpatterns = [
    path("firms/", a.AdminFirms.as_view()),
    path("firms/<int:pk>/", a.AdminFirm.as_view()),
    path("users/", a.AdminUsers.as_view()),
    path("users/<int:pk>/", a.AdminUser.as_view()),
    path("users/<int:pk>/reset-password/", a.AdminUserResetPassword.as_view()),
]
