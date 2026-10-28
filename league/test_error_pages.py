from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.db import OperationalError
from django.http import Http404
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import path

from . import error_views


def missing(request):
    raise Http404("private exception details")


def forbidden(request):
    raise PermissionDenied("private exception details")


def broken(request):
    raise OperationalError("private database details")


urlpatterns = [path("missing/", missing), path("forbidden/", forbidden), path("broken/", broken)]
handler403 = "league.error_views.permission_denied"
handler404 = "league.error_views.page_not_found"
handler500 = "league.error_views.server_error"


@override_settings(DEBUG=False, ROOT_URLCONF=__name__, ALLOWED_HOSTS=["testserver"])
class ErrorPageTests(SimpleTestCase):
    def test_handlers_render_correct_status_without_database_or_context_processors(self):
        client = Client(raise_request_exception=False)
        with patch("league.context_processors.league_context", side_effect=OperationalError("offline")):
            for url, status in (("/missing/", 404), ("/forbidden/", 403), ("/broken/", 500), ("/unknown/", 404)):
                with self.subTest(url=url):
                    response = client.get(url)
                    self.assertContains(response, "FASTLAP /", status_code=status)
                    self.assertContains(response, 'href="/"', status_code=status)
                    self.assertNotContains(response, "private exception", status_code=status)
                    self.assertNotContains(response, "private database", status_code=status)
                    self.assertIn("no-store", response["Cache-Control"])

    def test_csrf_failure_is_branded_and_does_not_expose_reason_or_replay_post(self):
        response = Client(enforce_csrf_checks=True).post("/forbidden/", {"secret": "hidden"}, secure=True)
        self.assertContains(response, "Действие не выполнено", status_code=403)
        self.assertContains(response, 'href="/forbidden/"', status_code=403)
        self.assertNotContains(response, "CSRF cookie", status_code=403)
        self.assertNotContains(response, "<form", status_code=403)

    def test_recovery_links_never_use_external_path_or_query_string(self):
        factory = RequestFactory()
        for path in ("//evil.example/", "/\\evil.example/"):
            request = factory.get("/")
            request.path = path
            response = error_views.csrf_failure(request, reason="sensitive")
            self.assertNotContains(response, "evil.example", status_code=403)
        request = factory.post("/forbidden/?next=https://evil.example/&secret=private-query-value")
        response = error_views.csrf_failure(request)
        self.assertNotContains(response, "private-query-value", status_code=403)
        self.assertNotContains(response, "evil.example", status_code=403)

    def test_server_error_on_post_does_not_offer_replay(self):
        response = error_views.server_error(RequestFactory().post("/broken/"))
        self.assertNotContains(response, "Открыть страницу заново", status_code=500)
