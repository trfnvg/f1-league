"""Public names are separate from unique sign-in handles."""
import re
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


def display_name(user):
    return user.get_full_name().strip() or user.username


def clean_handle(value, user=None):
    from .models import UserProfile
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9]{3,30}", value):
        raise ValidationError("Используй от 3 до 30 латинских букв и цифр, без пробелов и спецсимволов.")
    handles = UserProfile.objects.filter(handle__iexact=value)
    usernames = User.objects.filter(username__iexact=value)
    if user and user.pk:
        handles = handles.exclude(user=user)
        usernames = usernames.exclude(pk=user.pk)
    if handles.exists() or usernames.exists():
        raise ValidationError("Этот логин уже занят. Выбери другой.")
    return value


class HandleBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        value = username.strip()
        handle = value[1:] if value.startswith("@") else value
        user = User.objects.filter(league_profile__handle__iexact=handle).first()
        # Existing accounts keep their original sign-in name.
        if user is None and not value.startswith("@"):
            user = User.objects.filter(username=value).first()
        if user is None:
            User().set_password(password)
        elif user.check_password(password) and self.user_can_authenticate(user):
            return user
