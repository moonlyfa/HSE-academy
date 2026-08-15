from django.test import TestCase


class HealthEndpointTests(TestCase):
    """تست ساده برای اطمینان از بالا آمدن پروژه."""

    def test_health_returns_ok(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
