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

    def test_admin_and_public_login_use_same_raster_icons(self):
        for path in ('/accounts/login/', '/admin/login/'):
            response = self.client.get(path)
            self.assertContains(response, 'href="/favicon.ico?v=3"')
            self.assertContains(response, 'league/favicon-32.png')
            self.assertContains(response, 'league/favicon-48.png')
            self.assertNotContains(response, 'type="image/svg+xml"')
