# راهنمای استقرار روی سرور

این سند، سایت را از یک سرور خالی تا یک آدرس امنِ در حال کار می‌برد. همه
فایل‌های پیکربندی در پوشه `deploy/` آماده‌اند؛ اینجا فقط می‌گوییم هرکدام
کجا می‌روند و چرا.

**زمان لازم:** حدود دو ساعت برای بار اول.

---

## ۱. پیش‌نیازها

| مورد | حداقل | توضیح |
|---|---|---|
| سرور | ۲ هسته، ۴ گیگ رم، ۸۰ گیگ دیسک | دیسک را بر اساس حجم ویدیوها انتخاب کنید |
| سیستم‌عامل | Ubuntu 22.04 یا 24.04 | دستورهای این سند برای همین است |
| دامنه | ثبت‌شده و فعال | رکورد `A` آن به IP سرور اشاره کند |
| دسترسی | کاربر `sudo` | |

> **پیش از هر چیز، DNS را تنظیم کنید.** گرفتن گواهی SSL بدون اینکه دامنه
> به سرور اشاره کند شکست می‌خورد، و انتشار تغییرات DNS گاهی تا چند ساعت
> طول می‌کشد.

**حجم دیسک را دست‌کم نگیرید:** هر ساعت ویدیوی با کیفیت متوسط حدود یک
گیگابایت است، و پشتیبان‌ها هم روی همان دیسک ساخته می‌شوند.

---

## ۲. آماده‌سازی سرور

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-contrib \
                    nginx git curl

# کاربر جداگانه برای سایت. سایت هیچ‌وقت با کاربر root اجرا نمی‌شود:
# اگر روزی کسی از راه یک آسیب‌پذیری به پردازه برسد، جای زیادی برای
# رفتن نداشته باشد.
sudo adduser --system --group --home /srv/hse hse
sudo usermod -a -G www-data hse
```

### دیوار آتش

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

فقط سه در باز است: SSH، HTTP و HTTPS. دیتابیس و Gunicorn هیچ‌کدام از
بیرون قابل دسترسی نیستند (یکی روی `localhost` و دیگری روی Unix Socket).

---

## ۳. دیتابیس

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE hse_db;
CREATE USER hse_user WITH PASSWORD 'یک-رمز-قوی-و-تصادفی';

-- تنظیم‌های توصیه‌شده جنگو برای اتصال
ALTER ROLE hse_user SET client_encoding TO 'utf8';
ALTER ROLE hse_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE hse_user SET timezone TO 'Asia/Tehran';

GRANT ALL PRIVILEGES ON DATABASE hse_db TO hse_user;
\c hse_db
GRANT ALL ON SCHEMA public TO hse_user;
\q
```

---

## ۴. گرفتن کد

```bash
sudo mkdir -p /srv/hse && sudo chown hse:hse /srv/hse
sudo -u hse git clone <آدرس-مخزن-شما> /srv/hse
cd /srv/hse

sudo -u hse python3 -m venv .venv
sudo -u hse .venv/bin/pip install --upgrade pip
sudo -u hse .venv/bin/pip install -r requirements-prod.txt
```

---

## ۵. فایل تنظیمات `.env`

```bash
sudo -u hse cp .env.example .env
sudo -u hse nano /srv/hse/.env
sudo chmod 600 /srv/hse/.env
```

> **این فایل را از روی محیط توسعه کپی نکنید.** اگر `USE_MOCK_PAYMENT=True`
> با خودش بیاید، سایت **اصلاً بالا نمی‌آید** (محافظی که در فاز ۲۲ اضافه
> شد) — و این عمدی است: درگاه آزمایشی روی سایت واقعی یعنی هرکسی با یک
> کلیک «پرداخت موفق» دوره را رایگان برمی‌دارد.

مقادیری که حتماً باید عوض شوند:

```ini
DJANGO_SECRET_KEY=<با دستور پایین بسازید>
DJANGO_ALLOWED_HOSTS=hse.example.ir,www.hse.example.ir
DJANGO_CSRF_TRUSTED_ORIGINS=https://hse.example.ir,https://www.hse.example.ir
DATABASE_URL=postgres://hse_user:رمز@127.0.0.1:5432/hse_db

# آدرس پنل مدیریت را غیرقابل حدس کنید
DJANGO_ADMIN_URL=<یک-رشته-تصادفی>

# سرویس‌های واقعی
USE_MOCK_PAYMENT=False
USE_MOCK_SMS=False
USE_MOCK_IDENTITY=False
PAYMENT_PROVIDER=zarinpal
ZARINPAL_MERCHANT_ID=<کد پذیرنده شما>
SMS_PROVIDER=kavenegar
SMS_API_KEY=<کلید پنل پیامک>

# تحویل ویدیو با Nginx (بخش ۸ همین سند)
USE_X_ACCEL_REDIRECT=True
TRUST_X_FORWARDED_FOR=True

SITE_DOMAIN=hse.example.ir
```

ساخت کلید امنیتی:

```bash
sudo -u hse .venv/bin/python -c \
  "import secrets; print(secrets.token_urlsafe(64))"
```

---

## ۶. آماده‌سازی جنگو

```bash
cd /srv/hse
export DJANGO_SETTINGS_MODULE=config.settings.prod

sudo -u hse .venv/bin/python manage.py migrate
sudo -u hse .venv/bin/python manage.py createcachetable
sudo -u hse .venv/bin/python manage.py collectstatic --noinput
sudo -u hse .venv/bin/python manage.py setup_groups
sudo -u hse .venv/bin/python manage.py createsuperuser
```

> **`createcachetable` را فراموش نکنید.** شمارنده‌های محدودسازی نرخ
> (فاز ۲۱) در کش نگه داشته می‌شوند؛ بدون این جدول، سقف ورود و ثبت‌نام
> عملاً وجود نخواهد داشت.

### بررسی آمادگی

```bash
sudo -u hse .venv/bin/python manage.py check --deploy
sudo -u hse .venv/bin/python manage.py deploy_check
```

دستور اول تنظیمات خود جنگو را می‌سنجد؛ دستور دوم چیزهایی را که فقط این
پروژه می‌داند: جدول کش، فایل‌های ثابت، محل پوشه محافظت‌شده، کلید درگاه و
پنل پیامک. تا وقتی این دو تمیز نشده‌اند، جلوتر نروید.

---

## ۷. Gunicorn

```bash
sudo cp /srv/hse/deploy/gunicorn.socket  /etc/systemd/system/hse.socket
sudo cp /srv/hse/deploy/gunicorn.service /etc/systemd/system/hse.service
sudo systemctl daemon-reload
sudo systemctl enable --now hse.socket
sudo systemctl enable --now hse

sudo systemctl status hse
```

اگر بالا نیامد:

```bash
sudo journalctl -u hse -n 50 --no-pager
```

---

## ۸. Nginx

```bash
sudo cp /srv/hse/deploy/nginx.conf /etc/nginx/sites-available/hse
sudo nano /etc/nginx/sites-available/hse     # دامنه و مسیرها را عوض کنید
sudo ln -s /etc/nginx/sites-available/hse /etc/nginx/sites-enabled/hse
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t && sudo systemctl reload nginx
```

سه نکته در این فایل عمدی‌اند و نباید عوض شوند:

**`location /protected-internal/` با `internal`** — ویدیو و جزوه دوره‌ها
از این مسیر تحویل داده می‌شوند، اما `internal` یعنی از بیرون قابل صدا
زدن نیست. فقط وقتی کار می‌کند که جنگو پس از بررسی ثبت‌نام، هدر
`X-Accel-Redirect` بفرستد. **مسیر این بلوک باید دقیقاً با
`X_ACCEL_REDIRECT_PREFIX` در `.env` یکی باشد.**

**`proxy_set_header X-Forwarded-For $remote_addr;`** — نه
`$proxy_add_x_forwarded_for`. حالت دوم مقدار ساختگیِ خود کاربر را هم نگه
می‌دارد و سقف‌های محدودسازی نرخ با یک هدر دستی دور زده می‌شوند.

**`client_max_body_size 2048M`** — بدون آن، آپلود ویدیو از پنل مدیریت با
خطای ۴۱۳ رد می‌شود.

---

## ۹. گواهی SSL

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo mkdir -p /var/www/certbot

sudo certbot --nginx -d hse.example.ir -d www.hse.example.ir

# تمدید خودکار را امتحان کنید (بدون اینکه واقعاً تمدید کند)
sudo certbot renew --dry-run
```

گواهی Let's Encrypt هر ۹۰ روز تمدید می‌شود و `certbot` این کار را خودکار
انجام می‌دهد. `--dry-run` را حتماً یک‌بار اجرا کنید: بهتر است امروز
بفهمید تمدید کار نمی‌کند تا سه ماه دیگر که سایت با خطای گواهی بالا
می‌آید.

---

## ۱۰. پشتیبان‌گیری

```bash
sudo mkdir -p /var/backups/hse && sudo chown hse:hse /var/backups/hse

sudo cp /srv/hse/deploy/hse-backup.service /etc/systemd/system/
sudo cp /srv/hse/deploy/hse-backup.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hse-backup.timer

# یک‌بار دستی اجرا کنید تا مطمئن شوید کار می‌کند
sudo systemctl start hse-backup.service
journalctl -u hse-backup.service -n 20 --no-pager
ls -lh /var/backups/hse/
```

هر شب ساعت ۳ بامداد، چهار چیز پشتیبان گرفته می‌شود: دیتابیس،
`media/`، `protected_media/` و خود `.env`. نگهداری پیش‌فرض ۱۴ روز است.

> **پشتیبانی که روی همان سرور بماند، پشتیبان نیست.** اگر دیسک سرور
> بسوزد، پشتیبان هم با آن می‌رود. یک نسخه را بیرون ببرید:
>
> ```bash
> rsync -az /var/backups/hse/ user@backup-host:/backups/hse/
> ```

### بازگردانی

```bash
cd /srv/hse
sudo systemctl stop hse

# دیتابیس
sudo -u hse pg_restore --clean --if-exists \
     --dbname="postgres://hse_user:رمز@127.0.0.1:5432/hse_db" \
     /var/backups/hse/<تاریخ>/database.dump

# فایل‌ها
sudo -u hse tar -xzf /var/backups/hse/<تاریخ>/media.tar.gz -C /srv/hse
sudo -u hse tar -xzf /var/backups/hse/<تاریخ>/protected_media.tar.gz -C /srv/hse

sudo systemctl start hse
```

**هر چند ماه یک‌بار این کار را روی یک سرور آزمایشی تمرین کنید.** پشتیبانِ
امتحان‌نشده، پشتیبان نیست — و شب حادثه، وقت یاد گرفتن نیست.

---

## ۱۱. چرخش لاگ

```bash
sudo cp /srv/hse/deploy/logrotate-hse /etc/logrotate.d/hse
sudo logrotate -d /etc/logrotate.d/hse      # فقط بررسی، بدون اجرا
```

---

## ۱۲. به‌روزرسانی سایت

```bash
sudo -u hse /srv/hse/deploy/update.sh
```

این اسکریپت به همین ترتیب کار می‌کند: **پشتیبان → کد → کتابخانه‌ها →
بررسی تنظیمات → مهاجرت → فایل‌های ثابت → ری‌استارت.** اگر هر مرحله شکست
بخورد همان‌جا می‌ایستد و سایت با نسخه قبلی سرِپا می‌ماند.

---

## ۱۳. عیب‌یابی

| نشانه | معمولاً یعنی | بررسی کنید |
|---|---|---|
| خطای ۵۰۲ | Gunicorn بالا نیست | `systemctl status hse` و `journalctl -u hse -n 50` |
| سایت بدون CSS | فایل‌های ثابت جمع نشده یا مسیر Nginx اشتباه است | `collectstatic` و مسیر `alias` در بلوک `/static/` |
| سرویس اصلاً بالا نمی‌آید | تنظیم خطرناک در `.env` (مثلاً درگاه آزمایشی) | `journalctl -u hse -n 30` — پیام خطا صریح است |
| ویدیوی دوره باز نمی‌شود | مسیر `internal` با `.env` نمی‌خواند | `X_ACCEL_REDIRECT_PREFIX` و بلوک Nginx |
| آپلود ویدیو خطای ۴۱۳ | `client_max_body_size` کم است | بلوک HTTPS در `nginx.conf` |
| پیامک نمی‌رسد | کلید پنل یا اعتبار حساب | `deploy_check` و لاگ `hse.sms` |
| پرداخت به سایت برنمی‌گردد | آدرس بازگشت در پنل درگاه | پنل زرین‌پال و `SITE_DOMAIN` |
| سقف‌های محدودسازی کار نمی‌کنند | جدول کش ساخته نشده | `createcachetable` |

لاگ‌های مفید:

```bash
sudo journalctl -u hse -f                 # لاگ برنامه
sudo tail -f /var/log/nginx/hse-error.log # لاگ Nginx
sudo tail -f /srv/hse/logs/app.log        # لاگ پرداخت، ورود، گواهی
```

---

## ۱۴. چک‌لیست تحویل

پیش از اینکه بگویید «سایت بالاست»:

- [ ] `manage.py check --deploy` بدون هشدار
- [ ] `manage.py deploy_check` بدون خطا
- [ ] `https://دامنه/` باز می‌شود و قفل سبز دارد
- [ ] `http://دامنه/` به HTTPS هدایت می‌شود
- [ ] `certbot renew --dry-run` موفق
- [ ] ورود به پنل مدیریت با آدرس تغییر‌یافته
- [ ] یک ثبت‌نام واقعی با شماره خودتان (پیامک می‌رسد؟)
- [ ] یک **خرید واقعی** با مبلغ کم، تا پایان و دریافت دسترسی
- [ ] بازگشت وجه همان خرید از پنل درگاه
- [ ] آپلود یک ویدیو و پخش آن به‌عنوان دانشجوی ثبت‌نام‌شده
- [ ] همان ویدیو از حساب دیگری **قابل دیدن نباشد**
- [ ] یک آزمون کامل و صدور گواهی
- [ ] استعلام همان گواهی از حالت ناشناس (مرورگر مخفی)
- [ ] `hse-backup.timer` فعال و یک پشتیبان موفق ساخته شده
- [ ] یک نسخه پشتیبان بیرون از سرور
- [ ] `/sitemap.xml` و `/robots.txt` درست پاسخ می‌دهند
- [ ] آدرس `sitemap.xml` در Google Search Console ثبت شده
