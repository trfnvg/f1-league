from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from league.auth_views import FastlapLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", FastlapLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),  # ← добавили
    path("", include("league.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
