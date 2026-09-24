"""
تست‌های فاز ۲۲ — مسیر کامل دانشجو، از ثبت‌نام تا استعلام گواهی.

تست‌های هر اپ، بخش خودش را جداگانه می‌سنجند. اما چیزی که کسب‌وکار
می‌فروشد یک بخش نیست؛ یک **زنجیره** است:

    ثبت‌نام → تأیید پیامکی → احراز هویت → خرید → پرداخت → دسترسی
    → یادگیری → آزمون → گواهی → استعلام کارفرما

هر حلقه این زنجیره تست خودش را دارد، اما هیچ‌کدام نمی‌گویند «این‌ها به
هم وصل‌اند». همین تست است که می‌گوید. اگر روزی کسی امضای یک تابع میانی
را عوض کند و همه تست‌های واحد سبز بمانند، اینجا قرمز می‌شود.

تست دوم هم پشت‌روی همین است: **جایی که پول رد و بدل نشده، هیچ حلقه‌ای
باز نمی‌شود.**
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import OtpPurpose
from apps.accounts.services.sms import SmsResult
from apps.certificates.models import Certificate
from apps.courses.models import (
    CourseType,
    Course,
    CourseCategory,
    Enrollment,
    EnrollmentStatus,
    Lesson,
    Section,
)
from apps.exams.models import AttemptStatus, Exam, ExamAttempt, Question, QuestionOption
from apps.orders.models import Order, OrderStatus, Payment, PaymentStatus

User = get_user_model()

MOBILE = "09121234567"
NATIONAL_CODE = "0013542419"  # کد ملی معتبر (رقم کنترلی درست)
PASSWORD = "HseTech!2026"


class CapturingSms:
    """پیامک‌ها را نگه می‌دارد تا بتوانیم کد تأیید را بخوانیم."""

    name = "capture"
    sent: list[tuple[str, str]] = []

    def send(self, mobile, text):
        CapturingSms.sent.append((mobile, text))
        return SmsResult(success=True, provider=self.name)

    def send_otp(self, mobile, code):
        CapturingSms.sent.append((mobile, code))
        return SmsResult(success=True, provider=self.name)


@override_settings(ONLINE_COURSES_ENABLED=True)
class FullJourneyTests(TestCase):
    """
    یک دانشجو، از صفر تا گواهی قابل استعلام.

    عمداً از راه **صفحه‌های واقعی سایت** جلو می‌رود (نه صدا زدن مستقیم
    توابع)، چون چیزی که باید ثابت شود همین است: کاربر واقعی با همین
    کلیک‌ها به گواهی می‌رسد.
    """

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی صنعتی", slug="safety")
        cls.course = Course.objects.create(
            course_type=CourseType.OFFLINE_RECORDED,
            title="ایمنی کار در ارتفاع",
            slug="work-at-height",
            category=cls.category,
            price=2_000_000,
            duration_hours=16,
            certificate_available=True,
            exam_available=True,
            is_published=True,
        )

        section = Section.objects.create(course=cls.course, title="فصل اول")
        cls.lessons = [
            Lesson.objects.create(section=section, title=f"درس {index}", order=index)
            for index in range(1, 4)
        ]

        cls.exam = Exam.objects.create(
            course=cls.course,
            pass_score=60,
            shuffle_questions=False,
            shuffle_options=False,
            is_published=True,
        )
        cls.question = Question.objects.create(exam=cls.exam, text="سؤال نمونه")
        QuestionOption.objects.create(
            question=cls.question, text="پاسخ درست", is_correct=True, order=0
        )
        QuestionOption.objects.create(question=cls.question, text="پاسخ نادرست", order=1)

    def setUp(self):
        cache.clear()
        CapturingSms.sent = []
        patcher = patch(
            "apps.accounts.services.otp.get_sms_service", return_value=CapturingSms()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- گام‌های مسیر ---------------------------------------------------

    def last_code(self) -> str:
        self.assertTrue(CapturingSms.sent, "هیچ پیامکی ارسال نشده است.")
        return CapturingSms.sent[-1][1]

    def register(self) -> User:
        """ثبت‌نام چهار مرحله‌ای: موبایل، کد، کد ملی، رمز."""
        self.client.post(reverse("accounts:register"), {"mobile": MOBILE})
        self.client.post(
            reverse("accounts:register_verify"), {"code": self.last_code()}
        )
        self.client.post(
            reverse("accounts:register_identity"), {"national_code": NATIONAL_CODE}
        )
        self.client.post(
            reverse("accounts:register_complete"),
            {
                "first_name": "سارا",
                "last_name": "محمدی",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "accept_terms": "on",
            },
        )
        return User.objects.get(mobile=MOBILE)

    def buy_course(self) -> Order:
        """سبد خرید ← تسویه ← درگاه آزمایشی ← بازگشت و تأیید سمت‌سرور."""
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))

        order = Order.objects.get(user__mobile=MOBILE)
        self.client.post(reverse("orders:payment_start", args=[order.order_number]))

        payment = Payment.objects.get(order=order)
        self.client.post(
            reverse("orders:mock_gateway", args=[payment.authority]),
            {"decision": "success"},
        )
        self.client.get(
            reverse("orders:payment_callback"), {"Authority": payment.authority}
        )

        order.refresh_from_db()
        return order

    def finish_lessons(self) -> None:
        for lesson in self.lessons:
            self.client.post(
                reverse("courses:lesson_complete", args=[self.course.slug, lesson.pk]),
                {"completed": "1"},
            )

    def pass_exam(self) -> ExamAttempt:
        self.client.post(reverse("exams:start", args=[self.course.slug]))
        attempt = ExamAttempt.objects.get(exam=self.exam)

        answer = attempt.answers.first()
        correct = self.question.options.get(is_correct=True)
        self.client.post(
            reverse("exams:take", args=[attempt.pk]),
            {f"question_{answer.pk}": correct.pk},
        )

        attempt.refresh_from_db()
        return attempt

    # --- خودِ مسیر ------------------------------------------------------

    def test_a_student_goes_from_signup_to_a_verifiable_certificate(self):
        # ۱. ثبت‌نام
        user = self.register()
        self.assertTrue(user.is_mobile_verified)
        self.assertTrue(user.is_identity_verified)
        self.assertTrue(user.check_password(PASSWORD))

        # کاربر پس از تکمیل ثبت‌نام، وارد شده است.
        self.assertEqual(
            self.client.get(reverse("accounts:dashboard")).status_code, 200
        )

        # ۲. پیش از خرید، محتوا بسته است.
        lesson_url = self.lessons[0].get_absolute_url()
        self.assertContains(self.client.get(lesson_url), "ثبت‌نام در دوره")

        # ۳. خرید و پرداخت
        order = self.buy_course()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(
            Payment.objects.get(order=order).status, PaymentStatus.SUCCESS
        )

        # ۴. پرداخت یعنی ثبت‌نام؛ ثبت‌نام یعنی دسترسی.
        enrollment = Enrollment.objects.get(user=user, course=self.course)
        self.assertEqual(enrollment.status, EnrollmentStatus.ACTIVE)
        self.assertEqual(enrollment.order, order)
        self.assertEqual(self.client.get(lesson_url).status_code, 200)

        # ۵. گذراندن دوره
        self.finish_lessons()

        # ۶. آزمون
        attempt = self.pass_exam()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        self.assertTrue(attempt.is_passed)

        # ۷. گواهی
        self.client.post(reverse("certificates:issue", args=[self.course.slug]))
        certificate = Certificate.objects.get(user=user)
        self.assertEqual(certificate.holder_name, "سارا محمدی")
        self.assertEqual(certificate.score, attempt.score)

        # فایل PDF واقعاً ساخته می‌شود.
        pdf = self.client.get(certificate.get_pdf_url())
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        # ۸. کارفرما، بدون حساب کاربری، اصالت را بررسی می‌کند.
        self.client.logout()
        verification = self.client.get(
            reverse("core:certificate_verify"),
            {"code": certificate.certificate_code},
        )
        self.assertContains(verification, "این گواهی معتبر است")
        self.assertContains(verification, self.course.title)

    def test_an_unpaid_order_opens_nothing(self):
        """پشت‌روی همان زنجیره: بدون پرداخت، هیچ حلقه‌ای باز نمی‌شود."""
        user = self.register()

        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))
        order = Order.objects.get(user=user)

        # سفارش ساخته شده اما پرداخت نشده است.
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertFalse(Enrollment.objects.filter(user=user).exists())

        # درس بسته است.
        self.assertContains(
            self.client.get(self.lessons[0].get_absolute_url()), "ثبت‌نام در دوره"
        )

        # آزمون هم بسته است.
        self.client.post(reverse("exams:start", args=[self.course.slug]))
        self.assertFalse(ExamAttempt.objects.exists())

        # و گواهی صادر نمی‌شود.
        self.client.post(reverse("certificates:issue", args=[self.course.slug]))
        self.assertFalse(Certificate.objects.exists())

    def test_a_failed_payment_leaves_everything_closed(self):
        """کاربر تا درگاه می‌رود و پرداخت ناموفق می‌شود."""
        user = self.register()

        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))
        order = Order.objects.get(user=user)
        self.client.post(reverse("orders:payment_start", args=[order.order_number]))

        payment = Payment.objects.get(order=order)
        self.client.post(
            reverse("orders:mock_gateway", args=[payment.authority]),
            {"decision": "failed"},
        )
        self.client.get(
            reverse("orders:payment_callback"), {"Authority": payment.authority}
        )

        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertNotEqual(order.status, OrderStatus.PAID)
        self.assertFalse(Enrollment.objects.filter(user=user).exists())

    def test_claiming_success_in_the_callback_url_changes_nothing(self):
        """
        مهم‌ترین قاعده امنیتی پروژه، در مسیر واقعی.

        کاربر آدرس بازگشت را دستی می‌زند و ادعا می‌کند پرداخت موفق بوده.
        """
        user = self.register()
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))
        order = Order.objects.get(user=user)
        self.client.post(reverse("orders:payment_start", args=[order.order_number]))
        payment = Payment.objects.get(order=order)

        # بدون رفتن به درگاه، مستقیم با Status=OK برمی‌گردد.
        self.client.get(
            reverse("orders:payment_callback"),
            {"Authority": payment.authority, "Status": "OK"},
        )

        order.refresh_from_db()
        self.assertNotEqual(order.status, OrderStatus.PAID)
        self.assertFalse(Enrollment.objects.filter(user=user).exists())


@override_settings(ONLINE_COURSES_ENABLED=True)
class FreeCourseJourneyTests(TestCase):
    """دوره رایگان: همان زنجیره، بدون حلقه پرداخت."""

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="عمومی", slug="general")
        cls.course = Course.objects.create(
            course_type=CourseType.OFFLINE_RECORDED,
            title="آشنایی با HSE",
            slug="hse-intro",
            category=cls.category,
            price=0,
            certificate_available=True,
            exam_available=False,
            is_published=True,
        )
        section = Section.objects.create(course=cls.course, title="فصل")
        cls.lesson = Lesson.objects.create(section=section, title="درس")

        cls.user = User.objects.create_user(
            mobile="09127654321",
            password=PASSWORD,
            first_name="رضا",
            last_name="کریمی",
            is_mobile_verified=True,
            is_identity_verified=True,
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def test_free_course_still_needs_an_enrollment(self):
        """
        قاعده فاز ۱۴: دوره رایگان هم ثبت‌نام می‌خواهد.

        بدون آن معلوم نیست چه کسی دوره را گذرانده و گواهی به چه کسی
        باید داده شود.
        """
        response = self.client.get(self.lesson.get_absolute_url())
        self.assertContains(response, "ثبت‌نام رایگان")

        self.client.post(reverse("courses:enroll_free", args=[self.course.slug]))

        self.assertTrue(Enrollment.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get(self.lesson.get_absolute_url()).status_code, 200)

    def test_certificate_for_a_free_course_without_an_exam(self):
        self.client.post(reverse("courses:enroll_free", args=[self.course.slug]))
        self.client.post(
            reverse("courses:lesson_complete", args=[self.course.slug, self.lesson.pk]),
            {"completed": "1"},
        )

        self.client.post(reverse("certificates:issue", args=[self.course.slug]))

        certificate = Certificate.objects.get(user=self.user)
        self.assertIsNone(certificate.score)  # دوره آزمون نداشت
        self.assertTrue(certificate.is_valid)
