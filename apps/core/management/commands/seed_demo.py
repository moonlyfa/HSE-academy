"""
داده نمونه برای محیط توسعه.

هدف: بلافاصله بعد از نصب پروژه، صفحه اصلی پر و واقعی به نظر برسد تا بتوانید
طراحی را ببینید و تست کنید، بدون اینکه دستی ده‌ها رکورد بسازید.

اجرا:
    python manage.py seed_demo
    python manage.py seed_demo --reset   (اول داده‌های نمونه قبلی را پاک می‌کند)
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import FAQ, Banner, Feature, Partner, SiteSetting, Testimonial

FEATURES = [
    ("certificate", "گواهی قابل استعلام", "هر گواهی کد یکتا و صفحه استعلام عمومی دارد؛ کارفرما می‌تواند اصالت آن را بررسی کند."),
    ("users", "مدرسان متخصص", "تدریس توسط کارشناسان با سابقه اجرایی در صنایع نفت، گاز، پتروشیمی و ساختمان."),
    ("chart", "آموزش کاربردی", "محتوای دوره‌ها بر پایه سناریوهای واقعی محیط کار و الزامات قانونی تدوین شده است."),
    ("video", "کلاس آنلاین زنده", "امکان شرکت در کلاس زنده و پرسش مستقیم از مدرس، بدون نیاز به حضور فیزیکی."),
    ("download", "محتوای آفلاین", "دسترسی به ویدیوهای ضبط‌شده و جزوات دوره برای مرور در هر زمان."),
    ("lock", "پرداخت امن", "پرداخت از طریق درگاه بانکی معتبر و ثبت خودکار دسترسی پس از تأیید تراکنش."),
    ("headset", "پشتیبانی آموزشی", "پاسخ‌گویی به سؤالات علمی و فنی در طول دوره از طریق تیم پشتیبانی."),
    ("shield", "منطبق با استانداردها", "سرفصل‌ها بر اساس الزامات ISO 45001، HSE-MS و آیین‌نامه‌های وزارت کار طراحی شده‌اند."),
]

FAQS = [
    ("گواهی پایان دوره چگونه صادر می‌شود؟",
     "پس از تکمیل دوره و قبولی در آزمون پایانی، گواهی به‌صورت خودکار صادر می‌شود و از طریق داشبورد کاربری قابل دانلود است."),
    ("آیا گواهی قابل استعلام است؟",
     "بله. روی هر گواهی یک کد یکتا و QR درج می‌شود که از طریق صفحه «استعلام گواهی» در همین سایت قابل بررسی است."),
    ("تفاوت دوره آنلاین و آفلاین چیست؟",
     "دوره آنلاین در زمان مشخص و به‌صورت زنده برگزار می‌شود و امکان پرسش مستقیم از مدرس را دارد. دوره آفلاین از ویدیوهای ضبط‌شده تشکیل شده و در هر زمانی قابل مشاهده است."),
    ("اگر جلسه آنلاین را از دست بدهم چه می‌شود؟",
     "ویدیوی ضبط‌شده جلسات در داشبورد شما قرار می‌گیرد و تا پایان اعتبار دوره قابل مشاهده است."),
    ("امکان صدور فاکتور رسمی برای سازمان وجود دارد؟",
     "بله. برای ثبت‌نام گروهی و سازمانی، از طریق صفحه تماس با ما درخواست خود را ثبت کنید تا همکاران ما پیگیری کنند."),
    ("پیش‌نیاز شرکت در دوره‌ها چیست؟",
     "بیشتر دوره‌های پایه پیش‌نیاز خاصی ندارند. برای دوره‌های تخصصی، پیش‌نیازها در صفحه هر دوره ذکر شده است."),
]

TESTIMONIALS = [
    ("مریم احمدی", "کارشناس HSE، شرکت پتروشیمی",
     "دوره ارزیابی ریسک دقیقاً همان چیزی بود که برای کارم لازم داشتم. مثال‌ها واقعی بودند و مستقیماً در محل کار قابل استفاده."),
    ("رضا کریمی", "سرپرست ایمنی، پروژه عمرانی",
     "کیفیت کلاس آنلاین خیلی خوب بود و مدرس به همه سؤالات با حوصله جواب داد. گواهی هم سریع صادر شد."),
    ("سمیرا نوروزی", "مسئول بهداشت حرفه‌ای",
     "امکان دیدن دوباره ویدیوها کمک بزرگی بود. توانستم قبل از ممیزی سازمان، مطالب را دوره کنم."),
]

PARTNERS = [
    "شرکت ملی نفت", "پتروشیمی جم", "فولاد مبارکه",
    "دانشگاه صنعتی شریف", "سازمان نظام مهندسی", "شرکت گاز استانی",
]


class Command(BaseCommand):
    help = "ساخت داده نمونه برای محیط توسعه"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="حذف داده‌های نمونه قبلی قبل از ساخت مجدد",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("این دستور فقط در محیط توسعه اجرا می‌شود.")

        if options["reset"]:
            self._reset()

        self._seed_site_setting()
        self._seed_features()
        self._seed_banner()
        self._seed_faqs()
        self._seed_testimonials()
        self._seed_partners()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("داده نمونه با موفقیت ساخته شد."))
        self.stdout.write("حالا صفحه اصلی را ببینید: http://127.0.0.1:8000/")

    # ------------------------------------------------------------------
    def _reset(self):
        for model in (Feature, Banner, FAQ, Testimonial, Partner):
            deleted, _ = model.objects.all().delete()
            self.stdout.write(f"  پاک شد: {model._meta.verbose_name_plural} ({deleted})")

    def _seed_site_setting(self):
        site = SiteSetting.load()
        site.site_name = "آکادمی HSE"
        site.site_tagline = "آموزش تخصصی ایمنی، بهداشت و محیط زیست"
        site.phone = "021-12345678"
        site.email = "info@hse-academy.ir"
        site.address = "تهران، خیابان ولیعصر، پلاک ۱۰۰، واحد ۵"
        site.working_hours = "شنبه تا چهارشنبه، ۹ تا ۱۷"
        site.about_short = (
            "آکادمی تخصصی آموزش ایمنی، بهداشت و محیط زیست با هدف ارتقای "
            "سطح دانش کارشناسان HSE در صنایع کشور."
        )
        site.meta_description = (
            "دوره‌های تخصصی HSE، ایمنی صنعتی، ارزیابی ریسک و بهداشت حرفه‌ای "
            "با گواهی معتبر و قابل استعلام."
        )
        site.save()
        self.stdout.write(self.style.SUCCESS("✓ تنظیمات سایت"))

    def _seed_features(self):
        for index, (icon, title, description) in enumerate(FEATURES):
            Feature.objects.update_or_create(
                title=title,
                defaults={"icon": icon, "description": description, "order": index},
            )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(FEATURES)} مزیت"))

    def _seed_banner(self):
        now = timezone.now()
        Banner.objects.update_or_create(
            title="دوره جامع ایمنی صنعتی",
            defaults={
                "label": "دوره ویژه این ماه",
                "subtitle": (
                    "یک دوره کاربردی برای کارشناسان ایمنی: شناسایی خطر، "
                    "کنترل ریسک و تدوین دستورالعمل‌های ایمنی در محیط کار."
                ),
                "date_text": "شروع دوره: ابتدای ماه آینده",
                "cta_text": "مشاهده جزئیات دوره",
                "cta_url": "#courses",
                "starts_at": now - timezone.timedelta(days=1),
                "ends_at": now + timezone.timedelta(days=60),
                "order": 0,
            },
        )
        self.stdout.write(self.style.SUCCESS("✓ بنر ماهانه"))

    def _seed_faqs(self):
        for index, (question, answer) in enumerate(FAQS):
            FAQ.objects.update_or_create(
                question=question,
                defaults={"answer": answer, "order": index},
            )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(FAQS)} سؤال متداول"))

    def _seed_testimonials(self):
        for index, (name, job, quote) in enumerate(TESTIMONIALS):
            Testimonial.objects.update_or_create(
                full_name=name,
                defaults={"job_title": job, "quote": quote, "order": index},
            )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(TESTIMONIALS)} نظر دانشجو"))

    def _seed_partners(self):
        for index, name in enumerate(PARTNERS):
            Partner.objects.update_or_create(name=name, defaults={"order": index})
        self.stdout.write(self.style.SUCCESS(f"✓ {len(PARTNERS)} سازمان همکار"))
