"""Recovery pages independent of database-backed navigation and sessions."""
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.cache import patch_cache_control
from django.utils.http import url_has_allowed_host_and_scheme


def _page(request, status, title, message, *, retry=False):
    path = request.path
    retry_url = path if retry and path.startswith("/") and url_has_allowed_host_and_scheme(
        path, allowed_hosts=set(), require_https=request.is_secure()
    ) else None
    # No request context: a database outage must not run context processors.
    response = HttpResponse(render_to_string("errors/recovery.html", {
        "status": status, "title": title, "message": message, "retry_url": retry_url,
        "request_id": getattr(request, "request_id", "") if status in (403, 500) else "",
    }), status=status)
    patch_cache_control(response, no_store=True, private=True)
    response["Referrer-Policy"] = "same-origin"
    return response


def permission_denied(request, exception=None):
    return _page(request, 403, "Здесь нужен другой допуск",
        "Эта страница недоступна вашему аккаунту. Вернитесь на главную или войдите в другой аккаунт.")


def page_not_found(request, exception=None):
    return _page(request, 404, "Эта страница вне трассы",
        "Возможно, ссылка устарела или страница была удалена. Продолжим с главной.")


def server_error(request):
    return _page(request, 500, "Незапланированный пит-стоп",
        "На сервере произошла ошибка. Попробуйте открыть страницу чуть позже.",
        retry=request.method in ("GET", "HEAD"))


def csrf_failure(request, reason=""):
    return _page(request, 403, "Обновим страницу и продолжим",
        "Не удалось проверить безопасность запроса. Действие не выполнено. Откройте страницу заново и повторите его. Если ошибка повторяется, откройте сайт в Safari или Chrome и разрешите cookies для Fastlap.", retry=True)
