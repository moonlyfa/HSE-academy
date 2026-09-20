#!/usr/bin/env bash
# =============================================================================
#  به‌روزرسانی سایت روی سرور
#  ---------------------------------------------------------------------------
#  اجرا:  sudo -u hse /srv/hse/deploy/update.sh
#
#  ترتیب کارها عمدی است: اول پشتیبان، بعد کد، بعد مهاجرت دیتابیس، و
#  ری‌استارت در آخر. اگر هر مرحله شکست بخورد، اسکریپت همان‌جا می‌ایستد
#  (set -e) و سایت با نسخه قبلی سرِپا می‌ماند.
# =============================================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/srv/hse}"
cd "${PROJECT_DIR}"

echo "─── ۱. پشتیبان پیش از تغییر ───"
./deploy/backup.sh

echo "─── ۲. دریافت آخرین کد ───"
git pull --ff-only

echo "─── ۳. کتابخانه‌ها ───"
.venv/bin/pip install --quiet --requirement requirements-prod.txt

echo "─── ۴. بررسی سلامت تنظیمات ───"
# اگر تنظیمات سرور مشکلی دارد، پیش از دست زدن به دیتابیس معلوم شود.
.venv/bin/python manage.py check --deploy --settings=config.settings.prod
.venv/bin/python manage.py deploy_check --settings=config.settings.prod

echo "─── ۵. مهاجرت دیتابیس ───"
.venv/bin/python manage.py migrate --noinput --settings=config.settings.prod

echo "─── ۶. فایل‌های ثابت ───"
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings.prod

echo "─── ۷. ری‌استارت سرویس ───"
# ری‌استارت آرام: درخواست‌های در حال انجام تمام می‌شوند و بعد Worker
# جدید جایشان را می‌گیرد.
sudo systemctl reload hse || sudo systemctl restart hse

echo ""
echo "به‌روزرسانی انجام شد. سلامت سرویس:"
curl --silent --show-error --max-time 10 https://localhost/health/ --insecure || true
echo ""
