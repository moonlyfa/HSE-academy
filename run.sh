#!/usr/bin/env bash
# ===========================================================================
#   HSE Academy — اجرای سایت روی سیستم خودتان (لینوکس و مک)
#   ------------------------------------------------------------------------
#   اجرا:  ./run.sh
#
#   نسخه ویندوزی همین کار، فایل run.bat است (با دوبار کلیک).
# ===========================================================================

set -e

# اسکریپت از هر جایی اجرا شود، اول به پوشه خودش می‌رود.
cd "$(dirname "$0")"

PY=".venv/bin/python"

echo ""
echo "==========================================="
echo "   HSE Academy — اجرای سایت"
echo "==========================================="
echo ""

if [[ ! -x "${PY}" ]]; then
    echo "[۱/۴] ساخت محیط مجازی ..."
    python3 -m venv .venv
    echo "[۲/۴] نصب کتابخانه‌ها (بار اول چند دقیقه طول می‌کشد) ..."
    "${PY}" -m pip install --upgrade pip --quiet
    "${PY}" -m pip install -r requirements.txt --quiet
else
    echo "[۱/۴] محیط مجازی آماده است"
    echo "[۲/۴] بررسی کتابخانه‌ها ..."
    "${PY}" -m pip install -r requirements.txt --quiet
fi

if [[ ! -f .env ]]; then
    echo "      ساخت فایل تنظیمات .env"
    cp .env.example .env
fi

echo "[۳/۴] بروزرسانی دیتابیس ..."
"${PY}" manage.py migrate --noinput

# داده نمونه. کد خروج بررسی: ۲ = دیتابیس خالی (داده نمونه + حساب مدیر)،
# ۱ = دوره حضوری نیست (دیتابیس قدیمی؛ فقط داده نمونه)، ۰ = همه چیز هست.
set +e
"${PY}" -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev');django.setup();from apps.courses.models import Course;raise SystemExit(0 if Course.objects.filter(course_type='in_person').exists() else (1 if Course.objects.exists() else 2))" >/dev/null 2>&1
seed_state=$?
set -e
if [ "${seed_state}" -eq 2 ]; then
    echo "      ساخت داده نمونه (فقط بار اول) ..."
    "${PY}" manage.py seed_demo
    "${PY}" manage.py make_admin 09121234567 hse12345
    echo ""
    echo "      حساب مدیر:  09121234567  /  hse12345"
elif [ "${seed_state}" -eq 1 ]; then
    echo "      افزودن دوره‌های حضوری نمونه ..."
    "${PY}" manage.py seed_demo
fi

echo "[۴/۴] اجرای سایت ..."
echo ""
echo "   سایت:      http://127.0.0.1:8000/"
echo "   پنل مدیریت: http://127.0.0.1:8000/admin/"
echo ""
echo "   برای خاموش کردن: Ctrl+C"
echo ""

exec "${PY}" manage.py runserver
