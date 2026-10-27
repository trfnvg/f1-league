from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from league.auth_views import FastlapLoginView, FastlapPasswordResetView
from league.brand_views import favicon

urlpatterns = [
    path("favicon.ico", favicon, name="site_favicon"),
    path("admin/", admin.site.urls),
    path("accounts/login/", FastlapLoginView.as_view(), name="login"),
    path("accounts/password_reset/", FastlapPasswordResetView.as_view(), name="password_reset"),
    path("accounts/password_reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="registration/fastlap_password_reset_done.html"), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="registration/fastlap_password_reset_confirm.html"), name="password_reset_confirm"),
    path("accounts/reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="registration/fastlap_password_reset_complete.html"), name="password_reset_complete"),
    path("accounts/", include("django.contrib.auth.urls")),  # ← добавили
    path("", include("league.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
