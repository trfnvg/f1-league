from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from league.auth_views import FastlapLoginView, FastlapPasswordResetView
from league.brand_views import favicon
from league import browser_errors, health

handler403 = "league.error_views.permission_denied"
handler404 = "league.error_views.page_not_found"
handler500 = "league.error_views.server_error"

urlpatterns = [
    path("health/live/", health.live, name="health_live"),
    path("health/ready/", health.ready, name="health_ready"),
    path("diagnostics/browser-error/", browser_errors.report, name="browser_error"),
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
