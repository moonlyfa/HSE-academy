"""
تست‌های فاز ۱۷ — سامانه گواهی.

چهار چیز را نگه می‌دارند:

۱. گواهی فقط به کسی می‌رسد که **همه** شرط‌ها را دارد (ثبت‌نام، احراز
   هویت، تکمیل دوره و قبولی در آزمون).
۲. دو بار زدن دکمه، دو کد گواهی نمی‌سازد.
۳. لینک QR روی **توکن تصادفی** است، نه روی کد ترتیبی گواهی.
۴. گواهی باطل می‌شود، پاک نمی‌شود.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.certificates.issue import (
    certificate_card,
    check_eligibility,
    issue_certificate,
    next_certificate_code,
    revoke_certificate,
)
from apps.certificates.models import Certificate, CertificateStatus
from apps.certificates.pdf import fa, render_certificate
from apps.courses.enrollment import enroll
from apps.courses.models import Course, CourseCategory, Lesson, Section
from apps.courses.progress import set_completed
from apps.exams.grading import finish_attempt, save_answer, start_attempt
from apps.exams.models import Exam, Question, QuestionOption

User = get_user_model()


class CertificateTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره گواهی‌دار",
            slug="cert-course",
            category=cls.category,
            price=1_000_000,
            duration_hours=24,
            certificate_available=True,
            exam_available=False,
            is_published=True,
        )
        cls.section = Section.objects.create(course=cls.course, title="فصل اول")
        cls.lessons = [
            Lesson.objects.create(section=cls.section, title=f"درس {index}", order=index)
            for index in range(1, 4)
        ]

        cls.student = cls.make_student("09121234567")
        cls.stranger = User.objects.create_user(mobile="09127654321")

    @classmethod
    def make_student(cls, mobile):
        return User.objects.create_user(
            mobile=mobile,
            password="HseTech!2026",
            first_name="سارا",
            last_name="محمدی",
            is_mobile_verified=True,
            is_identity_verified=True,
        )

    def complete_course(self, user, course=None):
        course = course or self.course
        for lesson in Lesson.objects.filter(section__course=course):
            set_completed(user, lesson, True)

    def ready_student(self):
        """دانشجویی که همه شرط‌های گواهی را دارد."""
        enroll(self.student, self.course)
        self.complete_course(self.student)
        return self.student


class EligibilityTests(CertificateTestMixin, TestCase):
    def test_ready_student_is_eligible(self):
        self.assertTrue(check_eligibility(self.ready_student(), self.course).allowed)

    def test_course_without_certificate_offers_none(self):
        self.ready_student()
        self.course.certificate_available = False
        self.course.save(update_fields=["certificate_available"])

        result = check_eligibility(self.student, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "certificate_not_offered")

    def test_stranger_is_not_eligible(self):
        result = check_eligibility(self.stranger, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "purchase_required")

    def test_staff_without_enrollment_is_not_eligible(self):
        """دسترسی مدیر به محتوا، مدرک گذراندن دوره نیست."""
        staff = User.objects.create_user(
            mobile="09120000000",
            first_name="مدیر",
            last_name="سایت",
            is_staff=True,
            is_mobile_verified=True,
            is_identity_verified=True,
        )
        result = check_eligibility(staff, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "enrollment_required")

    def test_missing_name_blocks_issue(self):
        user = User.objects.create_user(
            mobile="09120000001", is_mobile_verified=True, is_identity_verified=True
        )
        enroll(user, self.course)
        self.complete_course(user)

        result = check_eligibility(user, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "name_missing")

    def test_unverified_mobile_blocks_issue(self):
        self.ready_student()
        self.student.is_mobile_verified = False
        self.student.save(update_fields=["is_mobile_verified"])

        self.assertEqual(
            check_eligibility(self.student, self.course).reason, "mobile_unverified"
        )

    def test_unverified_identity_blocks_issue(self):
        self.ready_student()
        self.student.is_identity_verified = False
        self.student.save(update_fields=["is_identity_verified"])

        self.assertEqual(
            check_eligibility(self.student, self.course).reason, "identity_unverified"
        )

    def test_unfinished_course_blocks_issue(self):
        enroll(self.student, self.course)
        set_completed(self.student, self.lessons[0], True)

        result = check_eligibility(self.student, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "course_not_completed")


class ExamRequirementTests(CertificateTestMixin, TestCase):
    """اگر دوره آزمون دارد، قبولی در آن شرط گواهی است."""

    def setUp(self):
        self.course.exam_available = True
        self.course.save(update_fields=["exam_available"])
        self.exam = Exam.objects.create(
            course=self.course, pass_score=50, shuffle_questions=False, is_published=True
        )
        question = Question.objects.create(exam=self.exam, text="سؤال")
        QuestionOption.objects.create(question=question, text="درست", is_correct=True)
        QuestionOption.objects.create(question=question, text="نادرست")
        self.question = question

        enroll(self.student, self.course)
        self.complete_course(self.student)

    def take_exam(self, *, correct: bool):
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.first()
        option = self.question.options.get(is_correct=correct)
        save_answer(attempt, answer, option.pk)
        return finish_attempt(attempt)

    def test_failed_exam_blocks_issue(self):
        self.take_exam(correct=False)

        result = check_eligibility(self.student, self.course)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "exam_not_passed")

    def test_passed_exam_allows_issue(self):
        self.take_exam(correct=True)
        self.assertTrue(check_eligibility(self.student, self.course).allowed)

    def test_score_is_copied_onto_the_certificate(self):
        attempt = self.take_exam(correct=True)
        certificate = issue_certificate(self.student, self.course)

        self.assertEqual(certificate.score, attempt.score)
        self.assertEqual(certificate.exam_attempt, attempt)

    def test_empty_exam_does_not_block_issue(self):
        """آزمونی که هنوز سؤال ندارد نباید جلوی گواهی را بگیرد."""
        Question.objects.all().delete()
        self.assertTrue(check_eligibility(self.student, self.course).allowed)


class IssueTests(CertificateTestMixin, TestCase):
    def test_holder_name_is_never_the_mobile_number(self):
        """روی گواهی باید نام واقعی چاپ شود، نه شماره تماس."""
        certificate = issue_certificate(self.ready_student(), self.course)
        self.assertNotIn(self.student.mobile, certificate.holder_name)

    def test_issue_snapshots_the_certificate_data(self):
        certificate = issue_certificate(self.ready_student(), self.course)

        self.assertEqual(certificate.holder_name, "سارا محمدی")
        self.assertEqual(certificate.course_title, "دوره گواهی‌دار")
        self.assertEqual(certificate.course_hours, 24)

    def test_snapshot_survives_later_edits(self):
        certificate = issue_certificate(self.ready_student(), self.course)

        self.course.title = "عنوان تازه دوره"
        self.course.save(update_fields=["title"])
        self.student.last_name = "نام تازه"
        self.student.save(update_fields=["last_name"])
        certificate.refresh_from_db()

        self.assertEqual(certificate.course_title, "دوره گواهی‌دار")
        self.assertEqual(certificate.holder_name, "سارا محمدی")

    def test_issuing_twice_returns_the_same_certificate(self):
        student = self.ready_student()
        first = issue_certificate(student, self.course)
        second = issue_certificate(student, self.course)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_ineligible_student_gets_nothing(self):
        enroll(self.student, self.course)  # دوره تکمیل نشده
        self.assertIsNone(issue_certificate(self.student, self.course))
        self.assertEqual(Certificate.objects.count(), 0)

    def test_code_is_sequential_within_the_year(self):
        first = issue_certificate(self.ready_student(), self.course)

        other = self.make_student("09121111111")
        enroll(other, self.course)
        self.complete_course(other)
        second = issue_certificate(other, self.course)

        year = first.certificate_code.split("-")[1]
        self.assertEqual(first.certificate_code, f"HSE-{year}-00001")
        self.assertEqual(second.certificate_code, f"HSE-{year}-00002")

    def test_revoked_certificate_does_not_free_its_number(self):
        first = issue_certificate(self.ready_student(), self.course)
        revoke_certificate(first, "صدور اشتباه")

        self.assertNotEqual(next_certificate_code(), first.certificate_code)

    def test_verification_url_uses_the_token_not_the_code(self):
        """لینک QR نباید با شمردن کدها قابل حدس باشد."""
        certificate = issue_certificate(self.ready_student(), self.course)
        url = certificate.get_verification_url()

        self.assertIn(certificate.verification_token, url)
        self.assertNotIn(certificate.certificate_code, url)

    def test_tokens_are_unique(self):
        first = issue_certificate(self.ready_student(), self.course)

        other = self.make_student("09121111111")
        enroll(other, self.course)
        self.complete_course(other)
        second = issue_certificate(other, self.course)

        self.assertNotEqual(first.verification_token, second.verification_token)


class RevokeAndValidityTests(CertificateTestMixin, TestCase):
    def setUp(self):
        self.certificate = issue_certificate(self.ready_student(), self.course)

    def test_new_certificate_is_valid(self):
        self.assertTrue(self.certificate.is_valid)
        self.assertEqual(self.certificate.status_label, "معتبر")

    def test_revoking_keeps_the_row(self):
        revoke_certificate(self.certificate, "دوره دوباره بررسی شد")

        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.status, CertificateStatus.REVOKED)
        self.assertFalse(self.certificate.is_valid)
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertEqual(self.certificate.revoke_reason, "دوره دوباره بررسی شد")

    def test_expired_certificate_is_not_valid(self):
        self.certificate.valid_until = timezone.localdate() - timedelta(days=1)
        self.certificate.save(update_fields=["valid_until"])

        self.assertFalse(self.certificate.is_valid)
        self.assertEqual(self.certificate.status_label, "منقضی‌شده")


class PdfTests(CertificateTestMixin, TestCase):
    def setUp(self):
        self.certificate = issue_certificate(self.ready_student(), self.course)

    def test_persian_text_is_reshaped_for_the_pdf(self):
        """بدون این مرحله، حروف فارسی جدا و برعکس چاپ می‌شوند."""
        self.assertNotEqual(fa("سلام"), "سلام")
        self.assertEqual(fa(""), "")

    def test_pdf_is_produced(self):
        content = render_certificate(
            self.certificate,
            verification_url="https://example.ir/certificate/verify/?token=x",
            site_name="HSE Tech",
        )

        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 2000)

    def test_revoked_certificate_pdf_is_still_produced(self):
        revoke_certificate(self.certificate, "ابطال")
        content = render_certificate(
            self.certificate, verification_url="https://example.ir/x", site_name="HSE"
        )
        self.assertTrue(content.startswith(b"%PDF"))


class CertificateViewTests(CertificateTestMixin, TestCase):
    def setUp(self):
        self.issue_url = reverse(
            "certificates:issue", kwargs={"slug": self.course.slug}
        )

    def test_issue_requires_post(self):
        self.ready_student()
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.issue_url).status_code, 405)

    def test_issue_creates_the_certificate(self):
        self.ready_student()
        self.client.force_login(self.student)

        response = self.client.post(self.issue_url)

        certificate = Certificate.objects.get(user=self.student)
        self.assertRedirects(response, certificate.get_absolute_url())

    def test_ineligible_student_cannot_force_an_issue(self):
        """دکمه‌ای که در صفحه نیست هم ممکن است دستی صدا زده شود."""
        enroll(self.student, self.course)
        self.client.force_login(self.student)

        self.client.post(self.issue_url)

        self.assertFalse(Certificate.objects.exists())

    def test_detail_page_shows_the_code(self):
        certificate = issue_certificate(self.ready_student(), self.course)
        self.client.force_login(self.student)

        response = self.client.get(certificate.get_absolute_url())

        self.assertContains(response, certificate.certificate_code)
        self.assertContains(response, "دانلود گواهی")

    def test_another_user_cannot_open_the_certificate(self):
        certificate = issue_certificate(self.ready_student(), self.course)
        self.client.force_login(self.stranger)

        self.assertEqual(
            self.client.get(certificate.get_absolute_url()).status_code, 404
        )

    def test_staff_can_open_any_certificate(self):
        certificate = issue_certificate(self.ready_student(), self.course)
        staff = User.objects.create_user(mobile="09120000002", is_staff=True)
        self.client.force_login(staff)

        self.assertEqual(
            self.client.get(certificate.get_absolute_url()).status_code, 200
        )

    def test_pdf_download_returns_a_pdf(self):
        certificate = issue_certificate(self.ready_student(), self.course)
        self.client.force_login(self.student)

        response = self.client.get(certificate.get_pdf_url())

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(certificate.certificate_code, response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_pdf_is_not_public(self):
        certificate = issue_certificate(self.ready_student(), self.course)
        self.client.force_login(self.stranger)

        self.assertEqual(self.client.get(certificate.get_pdf_url()).status_code, 404)

    def test_my_page_requires_login(self):
        response = self.client.get(reverse("certificates:my"))
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_my_page_lists_ready_courses_and_certificates(self):
        self.ready_student()
        self.client.force_login(self.student)

        response = self.client.get(reverse("certificates:my"))
        self.assertContains(response, self.issue_url)

        certificate = issue_certificate(self.student, self.course)
        response = self.client.get(reverse("certificates:my"))

        # دوره‌ای که گواهی‌اش صادر شده، دیگر در «آماده دریافت» نیست.
        self.assertNotContains(response, self.issue_url)
        self.assertContains(response, certificate.certificate_code)

    def test_course_page_shows_the_certificate_button(self):
        self.ready_student()
        self.client.force_login(self.student)

        response = self.client.get(self.course.get_absolute_url())

        self.assertContains(response, "دریافت گواهی")

    def test_course_page_hides_the_block_from_visitors(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertNotContains(response, "دریافت گواهی")

    def test_certificate_card_is_none_for_a_visitor(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(certificate_card(AnonymousUser(), self.course))


class VerificationHelperTests(TestCase):
    """کد را آن‌طور که آدم‌ها می‌نویسند بخوان، نه آن‌طور که ذخیره شده."""

    def test_persian_digits_are_understood(self):
        from apps.certificates.verification import normalize_code

        self.assertEqual(normalize_code("HSE-۱۴۰۵-۰۰۰۰۱"), "HSE-1405-00001")

    def test_case_spaces_and_dashes_are_normalized(self):
        from apps.certificates.verification import normalize_code

        self.assertEqual(normalize_code(" hse – 1405 – 00001 "), "HSE-1405-00001")
        self.assertEqual(normalize_code("hse_1405_00001"), "HSE-1405-00001")
        self.assertEqual(normalize_code(""), "")

    def test_name_masking_keeps_the_first_name(self):
        from apps.certificates.verification import mask_name

        self.assertEqual(mask_name("سارا محمدی"), "سارا م.")
        self.assertEqual(mask_name("محمد رضا حسینی"), "محمد رضا ح.")
        self.assertEqual(mask_name("سارا"), "س…")
        self.assertEqual(mask_name(""), "")


class PublicVerificationTests(CertificateTestMixin, TestCase):
    """
    صفحه عمومی استعلام.

    این تنها جای سایت است که بدون حساب کاربری به داده یک دانشجو نگاه
    می‌کند؛ تست‌ها هم دنبال همین‌اند: کارفرما جواب درست بگیرد، و کسی که
    کدها را می‌شمارد به نام و اطلاعات شخصی نرسد.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.certificate = issue_certificate(self.ready_student(), self.course)
        self.url = reverse("core:certificate_verify")

    def test_page_is_public_and_shows_the_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["result"])

    def test_valid_code_is_confirmed(self):
        response = self.client.get(self.url, {"code": self.certificate.certificate_code})

        self.assertContains(response, "این گواهی معتبر است")
        self.assertContains(response, self.certificate.course_title)

    def test_code_typed_with_persian_digits_still_matches(self):
        from apps.core.jalali import to_persian_digits

        response = self.client.get(
            self.url, {"code": to_persian_digits(self.certificate.certificate_code)}
        )
        self.assertContains(response, "این گواهی معتبر است")

    def test_unknown_code_says_not_found(self):
        response = self.client.get(self.url, {"code": "HSE-1405-99999"})

        self.assertContains(response, "پیدا نشد")
        self.assertIsNone(response.context["result"].certificate)

    def test_code_lookup_masks_the_holder_name(self):
        """کسی که کدها را می‌شمارد نباید به فهرست نام دانشجوها برسد."""
        response = self.client.get(self.url, {"code": self.certificate.certificate_code})

        self.assertContains(response, "سارا م.")
        self.assertNotContains(response, "سارا محمدی")

    def test_token_from_the_qr_shows_the_full_name(self):
        """کسی که QR را اسکن کرده، خودِ گواهی را در دست دارد."""
        response = self.client.get(
            self.url, {"token": self.certificate.verification_token}
        )

        self.assertContains(response, "سارا محمدی")
        self.assertTrue(response.context["result"].full_name_shown)

    def test_wrong_token_is_not_found(self):
        response = self.client.get(self.url, {"token": "not-a-real-token"})
        self.assertContains(response, "پیدا نشد")

    def test_revoked_certificate_says_so_with_its_reason(self):
        """«پیدا نشد» و «باطل شده» دو حرف کاملاً متفاوت به کارفرما می‌زنند."""
        revoke_certificate(self.certificate, "دوره دوباره بررسی شد")

        response = self.client.get(self.url, {"code": self.certificate.certificate_code})

        self.assertContains(response, "باطل شده")
        self.assertContains(response, "دوره دوباره بررسی شد")

    def test_expired_certificate_is_reported_as_expired(self):
        self.certificate.valid_until = timezone.localdate() - timedelta(days=1)
        self.certificate.save(update_fields=["valid_until"])

        response = self.client.get(self.url, {"code": self.certificate.certificate_code})

        self.assertContains(response, "به پایان رسیده")

    def test_no_personal_contact_data_leaks(self):
        response = self.client.get(
            self.url, {"token": self.certificate.verification_token}
        )

        self.assertNotContains(response, self.student.mobile)

    def test_results_are_not_indexed_by_search_engines(self):
        response = self.client.get(self.url, {"code": self.certificate.certificate_code})
        self.assertContains(response, 'name="robots" content="noindex"')

    def test_lookups_are_rate_limited(self):
        """بدون سقف، کدها را می‌شود یکی‌یکی امتحان کرد."""
        with self.settings(CERTIFICATE_LOOKUP_MAX_PER_HOUR=3):
            for _ in range(3):
                self.client.get(self.url, {"code": "HSE-1405-99999"})

            response = self.client.get(
                self.url, {"code": self.certificate.certificate_code}
            )

        self.assertContains(response, "تعداد استعلام‌های شما زیاد بوده است")
        self.assertNotContains(response, "این گواهی معتبر است")

    def test_browsing_the_page_does_not_count_against_the_limit(self):
        with self.settings(CERTIFICATE_LOOKUP_MAX_PER_HOUR=2):
            for _ in range(5):
                self.client.get(self.url)

            response = self.client.get(
                self.url, {"code": self.certificate.certificate_code}
            )

        self.assertContains(response, "این گواهی معتبر است")
