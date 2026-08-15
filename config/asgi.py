"""
پیکربندی ASGI.

فعلاً از آن استفاده نمی‌کنیم (پروژه همگام/Sync است) اما برای آینده نگه می‌داریم.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
