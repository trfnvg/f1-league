from pathlib import Path
from xml.etree import ElementTree

from django.test import TestCase, override_settings


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class BrowserIconTests(TestCase):
    def test_root_favicon_is_public_binary_and_supports_head(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/x-icon')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x00\x00\x01\x00'))
        self.assertIn('public', response['Cache-Control'])
        self.assertEqual(self.client.head('/favicon.ico').status_code, 200)
        self.assertEqual(self.client.post('/favicon.ico').status_code, 405)

    def test_home_admin_and_login_use_one_shared_versioned_tab_icon(self):
        for path in ('/', '/accounts/login/', '/admin/login/'):
            response = self.client.get(path)
            self.assertContains(response, 'rel="icon"', count=1)
            self.assertContains(response, 'href="/static/league/fastlap-tab-v4.ico"')
            self.assertNotContains(response, 'type="image/svg+xml"')

    def test_public_pages_share_outlined_wordmark_without_the_old_square(self):
        for path in ('/', '/calendar/', '/accounts/login/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, 'class="fl-wordmark"', count=3)
                self.assertContains(response, '/static/league/fastlap-wordmark.svg', count=3)
                self.assertContains(response, 'alt="Fastlap"', count=3)
                self.assertContains(response, 'class="fl-compactmark"', count=1)
                self.assertNotContains(response, 'class="fl-brandmark"')
                self.assertNotContains(response, 'fl-logo-orbit')

    def test_wordmark_is_original_local_paths_not_font_text_or_remote_images(self):
        folder = Path(__file__).parent / 'static/league'
        svg = ElementTree.parse(folder / 'fastlap-wordmark.svg').getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        self.assertEqual([node.attrib['data-letter'] for node in svg.findall('.//svg:path[@data-letter]', ns)], list('fastlap'))
        self.assertEqual(svg.findall('.//svg:text', ns), [])
        self.assertEqual(svg.findall('.//svg:image', ns), [])
        self.assertEqual(svg.findall('.//svg:script', ns), [])
        self.assertLess((folder / 'fastlap-wordmark.svg').stat().st_size, 5000)
        self.assertEqual(ElementTree.parse(folder / 'fastlap-monogram.svg').getroot().tag, '{http://www.w3.org/2000/svg}svg')
