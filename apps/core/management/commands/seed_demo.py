"""
داده نمونه برای محیط توسعه.

هدف: بلافاصله بعد از نصب پروژه، سایت پر و واقعی به نظر برسد تا بتوانید
طراحی را ببینید و تست کنید، بدون اینکه دستی ده‌ها رکورد بسازید.

اجرا:
    python manage.py seed_demo
    python manage.py seed_demo --reset   (اول داده‌های نمونه قبلی را پاک می‌کند)
"""

import io
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import InstructorProfile
from apps.core.models import FAQ, Feature, HeroSlide, Partner, SiteSetting, Testimonial
from apps.courses.models import (
    Course,
    CourseCategory,
    CourseLevel,
    CourseType,
    Lesson,
    LessonType,
    Section,
)

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

CATEGORIES = [
    ("HSE عمومی", "hse-general", "shield", "مبانی و مدیریت یکپارچه ایمنی، بهداشت و محیط زیست."),
    ("ایمنی صنعتی", "industrial-safety", "shield", "ایمنی در محیط‌های صنعتی، کارگاهی و پروژه‌های عمرانی."),
    ("ارزیابی ریسک", "risk-assessment", "chart", "شناسایی خطر و ارزیابی ریسک با روش‌های استاندارد."),
    ("بهداشت حرفه‌ای", "occupational-health", "users", "عوامل زیان‌آور محیط کار و کنترل آن‌ها."),
    ("محیط زیست", "environment", "book", "مدیریت پسماند، پایش آلاینده‌ها و الزامات زیست‌محیطی."),
    ("استانداردهای ISO", "iso-standards", "certificate", "ISO 45001، ISO 14001 و سایر استانداردهای مدیریتی."),
    ("مدیریت بحران", "crisis-management", "headset", "طرح واکنش در شرایط اضطراری و مدیریت بحران."),
    ("بازرسی تجهیزات", "equipment-inspection", "lock", "بازرسی فنی تجهیزات، جرثقیل و مخازن تحت فشار."),
    ("دوره‌های سازمانی", "corporate", "video", "دوره‌های اختصاصی متناسب با نیاز سازمان شما."),
]

# (نام، اسلاگ، تخصص، بیوگرافی)
INSTRUCTORS = [
    (
        "مهندس علی رضایی",
        "ali-rezaei",
        "کارشناس ارشد HSE، ۱۵ سال سابقه در صنایع نفت و گاز",
        "کارشناس ارشد ایمنی صنعتی با بیش از پانزده سال سابقه اجرایی در پالایشگاه‌ها "
        "و پروژه‌های پتروشیمی. مسئول استقرار سیستم مدیریت HSE در چند پروژه بزرگ ملی "
        "بوده و از سال ۱۳۹۴ به‌صورت تخصصی دوره‌های افسر HSE و ایمنی پیمانکاران را "
        "تدریس می‌کند.",
    ),
    (
        "دکتر مریم حسینی",
        "maryam-hosseini",
        "دکترای بهداشت حرفه‌ای، مدرس دانشگاه",
        "دارای دکترای بهداشت حرفه‌ای و عضو هیئت علمی دانشگاه. زمینه پژوهشی اصلی او "
        "شناسایی و کنترل عوامل زیان‌آور شیمیایی محیط کار است و سابقه همکاری با "
        "مراکز بهداشت صنعتی چند شرکت بزرگ را دارد.",
    ),
    (
        "مهندس سعید کاظمی",
        "saeed-kazemi",
        "ممیز ارشد ISO 45001، بازرس فنی تجهیزات",
        "ممیز ارشد استانداردهای ISO 45001 و ISO 14001 و بازرس فنی تجهیزات تحت فشار "
        "و بالابرها. تاکنون بیش از دویست ممیزی داخلی و شخص ثالث در صنایع مختلف "
        "انجام داده است.",
    ),
]

# (عنوان، اسلاگ، دسته، مدرس، نوع، سطح، ساعت، قیمت، تخفیف، روز تا شروع، منتخب)
COURSES = [
    ("دوره جامع افسر HSE", "hse-officer", "hse-general", 0, CourseType.ONLINE_LIVE, CourseLevel.INTERMEDIATE, 40, 4_800_000, 3_900_000, 12, True),
    ("ایمنی صنعتی مقدماتی", "industrial-safety-basics", "industrial-safety", 0, CourseType.ONLINE_LIVE, CourseLevel.BEGINNER, 24, 2_400_000, None, 20, True),
    ("ارزیابی ریسک به روش FMEA", "risk-assessment-fmea", "risk-assessment", 2, CourseType.HYBRID, CourseLevel.ADVANCED, 32, 3_600_000, 2_900_000, 30, True),
    ("شناسایی عوامل زیان‌آور محیط کار", "occupational-hazards", "occupational-health", 1, CourseType.OFFLINE_RECORDED, CourseLevel.INTERMEDIATE, 18, 1_900_000, None, None, False),
    ("مدیریت پسماند صنعتی", "industrial-waste", "environment", 1, CourseType.OFFLINE_RECORDED, CourseLevel.BEGINNER, 12, 1_200_000, None, None, False),
    ("تشریح الزامات ISO 45001", "iso-45001", "iso-standards", 2, CourseType.ONLINE_LIVE, CourseLevel.ADVANCED, 28, 3_200_000, None, 45, True),
    ("مبانی HSE برای پیمانکاران", "hse-for-contractors", "hse-general", 0, CourseType.ONLINE_LIVE, CourseLevel.BEGINNER, 16, 0, None, 8, False),
    ("طرح واکنش در شرایط اضطراری", "emergency-response", "crisis-management", 2, CourseType.HYBRID, CourseLevel.INTERMEDIATE, 20, 2_800_000, 2_200_000, 25, True),
    ("بازرسی جرثقیل و تجهیزات بالابر", "crane-inspection", "equipment-inspection", 2, CourseType.ONLINE_LIVE, CourseLevel.ADVANCED, 24, 3_400_000, None, 38, False),
    ("ایمنی کار در ارتفاع", "working-at-height", "industrial-safety", 0, CourseType.OFFLINE_RECORDED, CourseLevel.BEGINNER, 10, 950_000, None, None, False),
]

# ساختار نمونه محتوای دوره: (عنوان فصل، [(عنوان درس، نوع، دقیقه، پیش‌نمایش رایگان)])
CURRICULUM = [
    (
        "مقدمه و مفاهیم پایه",
        [
            ("معرفی دوره و سرفصل‌ها", LessonType.VIDEO, 8, True),
            ("تعریف HSE و جایگاه آن در سازمان", LessonType.VIDEO, 22, True),
            ("واژه‌نامه اصطلاحات تخصصی", LessonType.TEXT, 10, False),
        ],
    ),
    (
        "الزامات قانونی و استانداردها",
        [
            ("قانون کار و آیین‌نامه‌های حفاظت فنی", LessonType.VIDEO, 31, False),
            ("آشنایی با ISO 45001", LessonType.VIDEO, 27, False),
            ("چک‌لیست انطباق با الزامات", LessonType.FILE, 5, False),
        ],
    ),
    (
        "شناسایی خطر و ارزیابی ریسک",
        [
            ("روش‌های شناسایی خطر", LessonType.VIDEO, 35, False),
            ("ماتریس ارزیابی ریسک", LessonType.VIDEO, 29, False),
            ("تمرین عملی: ارزیابی یک کارگاه", LessonType.TEXT, 20, False),
        ],
    ),
    (
        "کنترل و پایش",
        [
            ("سلسله‌مراتب کنترل خطر", LessonType.VIDEO, 24, False),
            ("تجهیزات حفاظت فردی", LessonType.VIDEO, 18, False),
            ("جلسه پرسش و پاسخ زنده", LessonType.LIVE, 60, False),
        ],
    ),
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

# اسلایدهای نمونه: (عنوان، رنگ شروع، رنگ پایان، لینک)
# این‌ها فقط جای‌نگهدارند تا اسلایدر خالی نماند؛ تصاویر واقعی را از پنل
# مدیریت آپلود می‌کنید و هر کدام را نخواستید غیرفعال یا حذف کنید.
SLIDES = [
    ("دوره‌های تخصصی HSE", (15, 76, 58), (20, 66, 92), "/courses/"),
    ("تقویم آموزشی نیمه دوم سال", (20, 66, 92), (29, 90, 125), "/calendar/"),
    ("گواهی معتبر و قابل استعلام", (9, 48, 35), (224, 123, 22), "/certificate/verify/"),
    ("دوره ارزیابی ریسک", (26, 107, 82), (15, 76, 58), "/courses/?category=risk-assessment"),
    ("ایمنی صنعتی برای پیمانکاران", (20, 66, 92), (15, 76, 58), "/courses/?category=industrial-safety"),
    ("استانداردهای ISO 45001", (9, 48, 35), (29, 90, 125), "/courses/?category=iso-standards"),
    ("بهداشت حرفه‌ای در محیط کار", (30, 132, 73), (15, 76, 58), "/courses/?category=occupational-health"),
    ("دوره‌های سازمانی و درون‌سازمانی", (185, 97, 16), (15, 76, 58), "/contact/"),
    ("کلاس‌های آنلاین زنده", (29, 90, 125), (9, 48, 35), "/courses/?type=online_live"),
    ("محتوای آفلاین و همیشه در دسترس", (15, 76, 58), (26, 107, 82), "/courses/?type=offline_recorded"),
]

# رنگ گرادیان تصویر نمونه هر دسته‌بندی
CATEGORY_COLORS = {
    "hse-general": ((15, 76, 58), (26, 107, 82)),
    "industrial-safety": ((20, 66, 92), (29, 90, 125)),
    "risk-assessment": ((9, 48, 35), (20, 66, 92)),
    "occupational-health": ((26, 107, 82), (15, 76, 58)),
    "environment": ((30, 132, 73), (15, 76, 58)),
    "iso-standards": ((20, 66, 92), (15, 76, 58)),
    "crisis-management": ((185, 97, 16), (15, 76, 58)),
    "equipment-inspection": ((29, 90, 125), (9, 48, 35)),
    "corporate": ((15, 76, 58), (20, 66, 92)),
}

SYLLABUS = """مبانی و تعاریف پایه
الزامات قانونی و استانداردهای مرجع
شناسایی خطرات محیط کار
روش‌های ارزیابی و کنترل ریسک
تجهیزات حفاظت فردی
مستندسازی و گزارش‌نویسی
مطالعه موردی و تمرین عملی"""


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
        self._seed_slides()
        self._seed_features()
        self._seed_categories()
        instructors = self._seed_instructors()
        self._seed_courses(instructors)
        self._seed_faqs()
        self._seed_testimonials()
        self._seed_partners()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("داده نمونه با موفقیت ساخته شد."))
        self.stdout.write("حالا سایت را ببینید: http://127.0.0.1:8000/")

    # ------------------------------------------------------------------
    def _reset(self):
        # فصل‌ها و درس‌ها با حذف دوره خودکار پاک می‌شوند (on_delete=CASCADE)
        for model in (Course, CourseCategory, InstructorProfile, Feature, HeroSlide,
                      FAQ, Testimonial, Partner):
            deleted, _ = model.objects.all().delete()
            self.stdout.write(f"  پاک شد: {model._meta.verbose_name_plural} ({deleted})")

    def _seed_site_setting(self):
        site = SiteSetting.load()
        site.site_name = "HSE Tech"
        site.site_tagline = "آموزش تخصصی ایمنی، بهداشت و محیط زیست"
        site.phone = "021-12345678"
        site.email = "info@hsetech.ir"
        site.address = "تهران، خیابان ولیعصر، پلاک ۱۰۰، واحد ۵"
        site.working_hours = "شنبه تا چهارشنبه، ۹ تا ۱۷"
        site.hero_slider_interval_seconds = 6
        site.hero_slider_transition_ms = 1400
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

    def _make_gradient_image(self, width, height, start_rgb, end_rgb, label):
        """
        ساخت یک تصویر نمونه با گرادیان.

        این فقط جای‌نگهدار است تا اسلایدر خالی نماند؛ تصاویر واقعی را
        از پنل مدیریت آپلود می‌کنید.
        """
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (width, height), start_rgb)
        draw = ImageDraw.Draw(image)

        for x in range(width):
            ratio = x / max(width - 1, 1)
            color = tuple(
                int(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * ratio) for i in range(3)
            )
            draw.line([(x, 0), (x, height)], fill=color)

        # چند دایره کم‌رنگ برای اینکه تصویر کاملاً تخت نباشد
        for i, radius in enumerate((260, 180, 110)):
            cx = width - 320 - i * 90
            cy = height // 2
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=(255, 255, 255),
                width=2,
            )

        draw.text((70, height - 60), f"[ {label} ]", fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
        return ContentFile(buffer.getvalue())

    def _seed_slides(self):
        for index, (title, start_rgb, end_rgb, link) in enumerate(SLIDES):
            slide, created = HeroSlide.objects.update_or_create(
                title=title,
                defaults={"link_url": link, "order": index},
            )
            if created or not slide.image:
                slide.image.save(
                    f"demo-slide-{index + 1}.jpg",
                    self._make_gradient_image(1920, 650, start_rgb, end_rgb, "SAMPLE"),
                    save=True,
                )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(SLIDES)} اسلاید (تصاویر نمونه)"))

    def _seed_features(self):
        for index, (icon, title, description) in enumerate(FEATURES):
            Feature.objects.update_or_create(
                title=title,
                defaults={"icon": icon, "description": description, "order": index},
            )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(FEATURES)} مزیت"))

    def _seed_categories(self):
        for index, (name, slug, icon, description) in enumerate(CATEGORIES):
            CourseCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "icon": icon,
                    "description": description,
                    "order": index,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(CATEGORIES)} دسته‌بندی"))

    def _seed_instructors(self):
        instructors = []
        for index, (name, slug, specialty, bio) in enumerate(INSTRUCTORS):
            instructor, _ = InstructorProfile.objects.update_or_create(
                display_name=name,
                defaults={
                    "slug": slug,
                    "specialty": specialty,
                    "bio": bio,
                    "order": index,
                },
            )
            instructors.append(instructor)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(INSTRUCTORS)} مدرس"))
        return instructors

    def _seed_courses(self, instructors):
        today = timezone.now().date()

        for (title, slug, category_slug, instructor_index, course_type, level,
             hours, price, discount, days_ahead, featured) in COURSES:
            category = CourseCategory.objects.get(slug=category_slug)
            start_date = today + timedelta(days=days_ahead) if days_ahead else None

            course, _ = Course.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "category": category,
                    "instructor": instructors[instructor_index],
                    "course_type": course_type,
                    "level": level,
                    "duration_hours": hours,
                    "price": price,
                    "discount_price": discount,
                    "start_date": start_date,
                    "end_date": (
                        start_date + timedelta(days=hours // 4) if start_date else None
                    ),
                    "capacity": 30 if course_type != CourseType.OFFLINE_RECORDED else None,
                    "location": "آنلاین" if course_type != CourseType.HYBRID else "تهران و آنلاین",
                    "short_description": (
                        f"{title} با رویکرد کاربردی و منطبق بر الزامات قانونی، "
                        "همراه با مثال‌های واقعی محیط کار."
                    ),
                    "full_description": (
                        f"در دوره «{title}» مفاهیم پایه تا پیشرفته این حوزه به‌صورت گام‌به‌گام "
                        "آموزش داده می‌شود. تمرکز دوره بر کاربرد عملی مطالب در محیط کار است و "
                        "در پایان هر بخش، تمرین و مطالعه موردی ارائه می‌شود."
                    ),
                    "target_audience": (
                        "کارشناسان HSE، سرپرستان ایمنی، مسئولان بهداشت حرفه‌ای و "
                        "دانشجویان رشته‌های مرتبط."
                    ),
                    "prerequisites": "این دوره پیش‌نیاز خاصی ندارد.",
                    "syllabus": SYLLABUS,
                    "is_featured": featured,
                    "is_published": True,
                },
            )

            # تصویر نمونه فقط وقتی ساخته می‌شود که دوره هنوز تصویری ندارد،
            # تا تصویر واقعی آپلودشده توسط ادمین بازنویسی نشود.
            if not course.thumbnail:
                start_rgb, end_rgb = CATEGORY_COLORS.get(
                    category_slug, ((15, 76, 58), (20, 66, 92))
                )
                course.thumbnail.save(
                    f"demo-{slug}.jpg",
                    self._make_gradient_image(800, 450, start_rgb, end_rgb, "COURSE"),
                    save=True,
                )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(COURSES)} دوره (با تصویر نمونه)"))
        self._seed_curriculum()

    def _seed_curriculum(self):
        """
        برای دوره‌های منتخب، فصل و درس نمونه می‌سازد.

        همه دوره‌ها فصل‌بندی نمی‌شوند تا هر دو حالت سایت قابل دیدن باشد:
        دوره‌ای که ساختار کامل دارد، و دوره‌ای که فقط فهرست متنی سرفصل دارد.
        """
        courses = Course.objects.filter(is_featured=True)
        lesson_total = 0

        for course in courses:
            for section_index, (section_title, lessons) in enumerate(CURRICULUM):
                section, _ = Section.objects.update_or_create(
                    course=course,
                    title=section_title,
                    defaults={"order": section_index},
                )

                for lesson_index, (title, lesson_type, minutes, is_preview) in enumerate(lessons):
                    Lesson.objects.update_or_create(
                        section=section,
                        title=title,
                        defaults={
                            "lesson_type": lesson_type,
                            "order": lesson_index,
                            "duration_minutes": minutes,
                            "is_free_preview": is_preview,
                            "summary": f"{title} — بخشی از فصل «{section_title}».",
                            "content": (
                                "متن نمونه این درس. در نسخه واقعی، محتوای آموزشی یا "
                                "خلاصه ویدیو در این قسمت نوشته می‌شود."
                            ),
                        },
                    )
                    lesson_total += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ {courses.count()} دوره فصل‌بندی شد ({lesson_total} درس)"
            )
        )

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
