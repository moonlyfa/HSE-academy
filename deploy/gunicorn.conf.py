"""
پیکربندی Gunicorn — سرور اجرای پایتون در Production.

اجرا با این فایل:
    gunicorn config.wsgi:application -c deploy/gunicorn.conf.py

(در عمل، systemd این کار را می‌کند؛ نگاه کنید به deploy/gunicorn.service)
"""

import multiprocessing
import os

# --- محل گوش دادن ---
# Unix Socket به‌جای پورت TCP: از بیرون سرور اصلاً قابل دسترسی نیست و
# ارتباطش با Nginx هم سریع‌تر است.
bind = os.environ.get("GUNICORN_BIND", "unix:/run/hse/gunicorn.sock")

# --- تعداد Workerها ---
# قاعده متعارف: دو برابر هسته‌ها به‌علاوه یک. روی VPS کوچک، عدد بزرگ‌تر
# فقط حافظه مصرف می‌کند بدون اینکه چیزی سریع‌تر شود.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"

# هر Worker بعد از این تعداد درخواست ری‌استارت می‌شود. اگر جایی نشت حافظه
# باشد، این کار جلوی رشد بی‌پایان مصرف را می‌گیرد؛ jitter هم باعث می‌شود
# همه Workerها هم‌زمان ری‌استارت نشوند و سایت لحظه‌ای کند نشود.
max_requests = 1000
max_requests_jitter = 100

# --- زمان‌ها ---
# ساخت PDF گواهی و آپلود ویدیو ممکن است چند ده ثانیه طول بکشد.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive = 5

# --- لاگ ---
# خروجی به journald می‌رود (systemd) تا با journalctl قابل دیدن باشد.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# نام پردازه در خروجی ps و top، تا روی سروری با چند سرویس گم نشود.
proc_name = "hse-gunicorn"
