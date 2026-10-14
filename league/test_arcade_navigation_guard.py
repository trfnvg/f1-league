"""Navigation must also render before optional arcade routes are deployed."""
from pathlib import Path

from django.template import Context, Engine
from django.test import SimpleTestCase, override_settings


urlpatterns = []


class OptionalArcadeNavigationTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF=__name__)
    def test_missing_management_route_does_not_break_navigation(self):
        source = (Path(__file__).parent / "templates" / "base.html").read_text()
        start = source.index("{% url 'league:arcade_control' as arcade_control_url %}")
        link = source.index('href="{{ arcade_control_url }}"', start)
        end = source.index("{% endif %}", link) + len("{% endif %}")
        result = Engine().from_string(source[start:end]).render(Context())
        self.assertEqual(result.strip(), "")
