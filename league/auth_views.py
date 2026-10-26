import hashlib
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetView
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from .forms import AccountSettingsForm


class FastlapLoginView(LoginView):
    template_name = "registration/login_v2.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("league:home")
        return super().dispatch(request, *args, **kwargs)


class FastlapPasswordResetView(PasswordResetView):
    template_name = "registration/fastlap_password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not settings.EMAIL_HOST:
            form.add_error(None, "Восстановление по почте временно недоступно. Обратись к администратору.")
            return self.form_invalid(form)
        # One response for known and unknown addresses, with a bounded mail rate.
        digest = hashlib.sha256(form.cleaned_data["email"].strip().lower().encode()).hexdigest()
        if not cache.add(f"password-reset:{digest}", True, timeout=60):
            return redirect(self.success_url)
        # Never build recovery links from a caller-controlled Host header.
        public = urlsplit(settings.SITE_URL or "https://fastlap.ru")
        form.save(use_https=public.scheme == "https", domain_override=public.netloc,
            email_template_name=self.email_template_name, subject_template_name=self.subject_template_name,
            request=self.request, extra_email_context={"site_name": "Fastlap"})
        return redirect(self.success_url)


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request):
    form = AccountSettingsForm(request.POST or None, user=request.user,
        initial={"handle": request.user.league_profile.handle, "email": request.user.email})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                profile = request.user.league_profile
                profile.handle = form.cleaned_data["handle"]
                profile.save(update_fields=["handle"])
                request.user.email = form.cleaned_data["email"]
                request.user.save(update_fields=["email"])
        except IntegrityError:
            form.add_error("handle", "Этот логин уже занят. Выбери другой.")
        else:
            messages.success(request, "Настройки аккаунта сохранены.")
            return redirect("league:account_settings")
    return render(request, "registration/account_settings.html", {"form": form})
