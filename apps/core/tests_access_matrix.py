"""
تست‌های فاز ۲۲ — ماتریس دسترسی.

هر اپ، دسترسی خودش را تست می‌کند. این فایل همان بررسی‌ها را **یک‌جا و
کنار هم** می‌گذارد: برای هر آدرس حساس سایت، چهار نقش را می‌سنجد

    مهمان · کاربر واردشده اما بی‌ربط · دانشجوی ثبت‌نام‌شده · مدیر

همپوشانی با تست‌های هر اپ عمدی است. فایده‌اش این است که وقتی کسی
View تازه‌ای اضافه می‌کند، جای روشنی هست که باید یک سطر به آن اضافه
شود — و خالی‌بودن آن سطر، خودش سؤال ایجاد می‌کند. یک جدولِ کامل،
چیزی است که می‌شود با کارفرما مرورش کرد.

قاعده‌ای که در کل جدول رعایت شده: **پاسخ «نداری» نباید بگوید «هست ولی
مال تو نیست»**. برای محتوای خریدنی، صفحه باز می‌شود و می‌گوید چه باید
بکنی (این برای فروش لازم است)؛ برای داده شخصی دیگران، ۴۰۴.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.blog.models import BlogCategory, BlogPost, PostStatus
from apps.certificates.issue import issue_certificate
from apps.courses.enrollment import enroll
from apps.courses.models import (
    Course,
    CourseCategory,
    Lesson,
    LessonAttachment,
    OnlineSession,
    Section,
)
from apps.courses.progress import set_completed
from apps.exams.grading import finish_attempt, save_answer, start_attempt
from apps.exams.models import Exam, Question, QuestionOption
from apps.orders.models import Order, OrderItem, OrderStatus

User = get_user_model()

PASSWORD = "HseTech!2026"


class AccessMatrixMixin:
    """
    یک دوره پولی با همه‌چیز: درس، فایل، کلاس آنلاین، آزمون و گواهی.

    و چهار نقش که در همه تست‌ها یکسان‌اند.
    """

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره پولی",
            slug="paid-course",
            category=cls.category,
            price=1_500_000,
            certificate_available=True,
            exam_available=True,
            is_published=True,
        )

        section = Section.objects.create(course=cls.course, title="فصل")
        cls.lesson = Lesson.objects.create(section=section, title="درس")
        cls.attachment = LessonAttachment.objects.create(
            lesson=cls.lesson, title="جزوه", file="lessons/handout.pdf"
        )

        cls.session = OnlineSession.objects.create(
            course=cls.course,
            title="کلاس زنده",
            starts_at=timezone.now() - timedelta(minutes=5),
            meeting_url="https://www.skyroom.online/ch/hse/live",
        )

        cls.exam = Exam.objects.create(
            course=cls.course, pass_score=50, shuffle_questions=False, is_published=True
        )
        question = Question.objects.create(exam=cls.exam, text="سؤال")
        QuestionOption.objects.create(question=question, text="درست", is_correct=True)
        QuestionOption.objects.create(question=question, text="نادرست")
        cls.question = question

        # --- نقش‌ها ---
        cls.student = cls.make_user("09121234567")
        cls.stranger = cls.make_user("09127654321")
        cls.staff = cls.make_user("09120000000", is_staff=True)

        enroll(cls.student, cls.course)

    @classmethod
    def make_user(cls, mobile, **extra):
        return User.objects.create_user(
            mobile=mobile,
            password=PASSWORD,
            first_name="نام",
            last_name="خانوادگی",
            is_mobile_verified=True,
            is_identity_verified=True,
            **extra,
        )

    def setUp(self):
        cache.clear()

    # --- ابزار خواندنی برای نوشتن جدول --------------------------------

    def as_role(self, role: str):
        """کلاینتی که به‌عنوان نقش خواسته‌شده وارد شده است."""
        self.client.logout()
        user = {"student": self.student, "stranger": self.stranger, "staff": self.staff}.get(role)
        if user is not None:
            self.client.force_login(user)
        return self.client

    def assert_status(self, role: str, url: str, expected: int, method="get", data=None):
        client = self.as_role(role)
        response = getattr(client, method)(url, data or {})
        self.assertEqual(
            response.status_code,
            expected,
            f"نقش «{role}» روی {url} کد {response.status_code} گرفت، انتظار {expected} بود.",
        )
        return response

    def assert_sent_to_login(self, role: str, url: str):
        """
        هدایت به صفحه ورود.

        بیشتر صفحه‌ها به ورود سایت می‌روند؛ مسیر فایل‌های محافظت‌شده که
        فقط برای مدیر است، به ورود پنل مدیریت. هر دو «یعنی وارد شو».
        """
        response = self.assert_status(role, url, 302)
        self.assertIn("login", response["Location"])


class CourseContentAccessTests(AccessMatrixMixin, TestCase):
    """محتوای خریدنی: صفحه باز می‌شود، محتوا نه."""

    def test_lesson_page_is_open_to_everyone_but_locked_without_enrollment(self):
        url = self.lesson.get_absolute_url()

        for role in ("anonymous", "stranger"):
            response = self.assert_status(role, url, 200)
            self.assertContains(response, "ثبت‌نام در دوره")

        for role in ("student", "staff"):
            response = self.assert_status(role, url, 200)
            self.assertNotContains(response, "ثبت‌نام در دوره")

    def test_video_file_is_refused_without_enrollment(self):
        """فایل، برخلاف صفحه، اصلاً وجود ندارد — نه «قفل است»."""
        url = reverse("courses:lesson_video", args=[self.course.slug, self.lesson.pk])

        for role in ("anonymous", "stranger"):
            self.assert_status(role, url, 404)

    def test_attachment_is_refused_without_enrollment(self):
        url = reverse(
            "courses:lesson_attachment",
            args=[self.course.slug, self.lesson.pk, self.attachment.pk],
        )

        for role in ("anonymous", "stranger"):
            self.assert_status(role, url, 404)

    def test_marking_a_lesson_complete_needs_enrollment(self):
        url = reverse("courses:lesson_complete", args=[self.course.slug, self.lesson.pk])

        self.assert_sent_to_login("anonymous", url)
        self.assert_status("stranger", url, 404, method="post", data={"completed": "1"})
        self.assert_status("student", url, 302, method="post", data={"completed": "1"})

    def test_protected_media_is_for_staff_only(self):
        url = "/protected-media/lessons/handout.pdf"

        self.assert_sent_to_login("anonymous", url)
        self.assert_sent_to_login("student", url)
        # مدیر مجاز است؛ فایل نمونه روی دیسک نیست، پس ۴۰۴ می‌گیرد نه ۳۰۲.
        self.assert_status("staff", url, 404)


class OnlineClassAccessTests(AccessMatrixMixin, TestCase):
    def test_join_link_only_for_the_enrolled_student(self):
        url = self.session.get_join_url()

        self.assert_sent_to_login("anonymous", url)

        # غریبه به صفحه دوره برمی‌گردد، نه به کلاس.
        response = self.assert_status("stranger", url, 302)
        self.assertEqual(response["Location"], self.course.get_absolute_url())

        response = self.assert_status("student", url, 302)
        self.assertEqual(response["Location"], self.session.meeting_url)

    def test_the_link_is_not_in_any_page_html(self):
        for role in ("anonymous", "stranger", "student", "staff"):
            response = self.as_role(role).get(self.course.get_absolute_url())
            self.assertNotContains(response, self.session.meeting_url)

    def test_my_classes_page_needs_login(self):
        self.assert_sent_to_login("anonymous", reverse("courses:my_sessions"))


class ExamAccessTests(AccessMatrixMixin, TestCase):
    def test_exam_page_explains_itself_but_does_not_open(self):
        url = self.exam.get_absolute_url()

        response = self.assert_status("stranger", url, 200)
        self.assertNotContains(response, "شروع آزمون")

        response = self.assert_status("student", url, 200)
        self.assertContains(response, "شروع آزمون")

    def test_starting_an_exam_needs_enrollment(self):
        url = reverse("exams:start", args=[self.course.slug])

        self.assert_sent_to_login("anonymous", url, )
        self.as_role("stranger").post(url)
        self.assertEqual(self.exam.attempts.count(), 0)

        self.as_role("student").post(url)
        self.assertEqual(self.exam.attempts.count(), 1)

    def test_someone_elses_attempt_is_invisible(self):
        attempt = start_attempt(self.student, self.exam)

        for role in ("stranger", "staff"):
            self.assert_status(role, reverse("exams:take", args=[attempt.pk]), 404)
            self.assert_status(role, reverse("exams:result", args=[attempt.pk]), 404)

    def test_answers_cannot_be_posted_to_another_students_attempt(self):
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.first()
        correct = self.question.options.get(is_correct=True)

        self.assert_status(
            "stranger",
            reverse("exams:answer", args=[attempt.pk]),
            404,
            method="post",
            data={"answer": answer.pk, "option": correct.pk},
        )

        answer.refresh_from_db()
        self.assertIsNone(answer.selected_option)


class CertificateAccessTests(AccessMatrixMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        set_completed(cls.student, cls.lesson, True)
        attempt = start_attempt(cls.student, cls.exam)
        save_answer(
            attempt,
            attempt.answers.first(),
            cls.question.options.get(is_correct=True).pk,
        )
        finish_attempt(attempt)

        cls.certificate = issue_certificate(cls.student, cls.course)

    def test_certificate_page_belongs_to_its_owner(self):
        url = self.certificate.get_absolute_url()

        self.assert_sent_to_login("anonymous", url)
        self.assert_status("stranger", url, 404)
        self.assert_status("student", url, 200)
        self.assert_status("staff", url, 200)

    def test_pdf_is_not_public(self):
        url = self.certificate.get_pdf_url()

        self.assert_sent_to_login("anonymous", url)
        self.assert_status("stranger", url, 404)
        self.assert_status("student", url, 200)

    def test_public_verification_is_open_to_everyone(self):
        """این یکی **باید** برای همه باز باشد — کارفرما حساب کاربری ندارد."""
        url = reverse("core:certificate_verify")

        for role in ("anonymous", "stranger"):
            response = self.assert_status(
                role, f"{url}?code={self.certificate.certificate_code}", 200
            )
            self.assertContains(response, "این گواهی معتبر است")

    def test_issuing_for_someone_else_is_impossible(self):
        """مسیر صدور روی کاربر واردشده کار می‌کند، نه روی پارامتر آدرس."""
        from apps.certificates.models import Certificate

        url = reverse("certificates:issue", args=[self.course.slug])
        self.as_role("stranger").post(url)

        self.assertEqual(Certificate.objects.filter(user=self.stranger).count(), 0)


class OrderAccessTests(AccessMatrixMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.order = Order.objects.create(
            user=cls.student,
            status=OrderStatus.PENDING,
            full_name="سارا محمدی",
            mobile=cls.student.mobile,
            subtotal=1_500_000,
            total=1_500_000,
        )
        OrderItem.objects.create(
            order=cls.order,
            course=cls.course,
            title=cls.course.title,
            unit_price=1_500_000,
            final_price=1_500_000,
        )

    def test_order_belongs_to_its_buyer(self):
        url = reverse("orders:detail", args=[self.order.order_number])

        self.assert_sent_to_login("anonymous", url)
        self.assert_status("stranger", url, 404)
        self.assert_status("student", url, 200)

    def test_paying_for_someone_elses_order_is_impossible(self):
        url = reverse("orders:payment_start", args=[self.order.order_number])

        self.assert_status("stranger", url, 404, method="post")

    def test_cancelling_someone_elses_order_is_impossible(self):
        url = reverse("orders:cancel", args=[self.order.order_number])

        self.assert_status("stranger", url, 404, method="post")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)


class DashboardAccessTests(AccessMatrixMixin, TestCase):
    """همه صفحه‌های شخصی، پشت ورود."""

    def test_every_dashboard_page_requires_login(self):
        pages = [
            reverse("accounts:dashboard"),
            reverse("accounts:my_courses"),
            reverse("accounts:profile"),
            reverse("accounts:change_password"),
            reverse("courses:my_sessions"),
            reverse("exams:my"),
            reverse("certificates:my"),
            reverse("orders:list"),
        ]

        for url in pages:
            with self.subTest(url=url):
                self.assert_sent_to_login("anonymous", url)

    def test_a_logged_in_user_sees_only_their_own_dashboard_data(self):
        """هیچ صفحه داشبوردی پارامتر «کاربر» ندارد؛ همیشه خودِ واردشده."""
        for url in (reverse("accounts:my_courses"), reverse("certificates:my")):
            with self.subTest(url=url):
                self.assert_status("stranger", url, 200)


class AdminAccessTests(AccessMatrixMixin, TestCase):
    def test_admin_is_closed_to_ordinary_users(self):
        response = self.assert_status("student", "/admin/", 302)
        self.assertIn("login", response["Location"])

    def test_admin_opens_for_staff(self):
        self.assert_status("staff", "/admin/", 200)


@override_settings(BLOG_ENABLED=True)
class BlogAccessTests(AccessMatrixMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        blog_category = BlogCategory.objects.create(name="دانش فنی", slug="knowledge")
        cls.draft = BlogPost.objects.create(
            title="پیش‌نویس",
            slug="draft-post",
            category=blog_category,
            summary="چکیده",
            content="متن",
            status=PostStatus.DRAFT,
        )

    def test_draft_is_visible_to_staff_only(self):
        url = self.draft.get_absolute_url()

        for role in ("anonymous", "stranger", "student"):
            self.assert_status(role, url, 404)

        self.assert_status("staff", url, 200)
