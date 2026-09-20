@echo off
REM ===========================================================================
REM   HSE Academy - local run script (Windows)
REM   ------------------------------------------------------------------------
REM   اجرای سایت روی سیستم خودتان: کافی است روی همین فایل دوبار کلیک کنید.
REM
REM   این فایل خودش می‌داند در کدام پوشه است (%~dp0)، پس مهم نیست پروژه را
REM   کجا کپی کرده‌اید و از کدام پوشه اجرایش می‌کنید.
REM ===========================================================================

chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ===========================================
echo    HSE Academy - starting local site
echo ===========================================
echo.

REM --- 1. Virtual environment -------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment ...
    python -m venv .venv
    if errorlevel 1 goto no_python

    echo [2/4] Installing packages ^(first time takes a few minutes^) ...
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if errorlevel 1 goto pip_failed
) else (
    echo [1/4] Virtual environment: OK
    echo [2/4] Checking packages ...
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
)

REM --- 2. Settings file --------------------------------------------------
if not exist ".env" (
    echo       Creating .env from .env.example
    copy /y .env.example .env >nul
)

REM --- 3. Database -------------------------------------------------------
REM migrate هر بار اجرا می‌شود چون سریع است و اگر کد تازه‌ای گرفته باشید،
REM جدول‌های جدید را می‌سازد. اگر چیزی برای انجام نباشد، کاری نمی‌کند.
echo [3/4] Updating database ...
.venv\Scripts\python.exe manage.py migrate --noinput
if errorlevel 1 goto migrate_failed

REM --- 3b. Demo data (only when the database is empty) -------------------
REM اولین اجرا نباید سایت خالی نشان بدهد؛ اگر هیچ دوره‌ای نیست، داده
REM نمونه و یک حساب مدیر ساخته می‌شود.
.venv\Scripts\python.exe -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev');django.setup();from apps.courses.models import Course;raise SystemExit(0 if Course.objects.exists() else 1)" >nul 2>&1
if errorlevel 1 (
    echo       Loading demo data ^(first run only^) ...
    .venv\Scripts\python.exe manage.py seed_demo
    .venv\Scripts\python.exe manage.py make_admin 09121234567 hse12345
    echo.
    echo       Admin login:  09121234567  /  hse12345
)

REM --- 4. Run ------------------------------------------------------------
echo [4/4] Starting server ...
echo.
echo   Site:  http://127.0.0.1:8000/
echo   Admin: http://127.0.0.1:8000/admin/
echo.
echo   Press Ctrl+C to stop, or just close this window.
echo.

REM مرورگر چند ثانیه بعد باز می‌شود تا سرور فرصت بالا آمدن داشته باشد.
start "browser" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/"

.venv\Scripts\python.exe manage.py runserver
goto end

:no_python
echo.
echo   ERROR: Python not found.
echo   Install Python 3.11+ from python.org and tick "Add Python to PATH".
echo.
pause
goto end

:pip_failed
echo.
echo   ERROR: Installing packages failed. Check your internet connection.
echo.
pause
goto end

:migrate_failed
echo.
echo   ERROR: Database update failed. Send the message above to support.
echo.
pause

:end
