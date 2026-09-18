"""
تست‌های فاز ۱۶ — سامانه آزمون.

سه چیز را نگه می‌دارند:

۱. **هیچ‌کس بدون ثبت‌نام وارد آزمون نمی‌شود.**
۲. **مهلت آزمون در سرور اجرا می‌شود**، نه در مرورگر — پاسخی که بعد از
   مهلت برسد پذیرفته نمی‌شود.
۳. **کارنامه ثبت‌شده دیگر تغییر نمی‌کند**، حتی اگر سؤال یا نمره قبولی
   آزمون بعداً عوض شود.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.enrollment import enroll, revoke
from apps.courses.models import Course, CourseCategory, Lesson, Section
from apps.exams.access import attempts_left, check_can_start, check_exam_access
from apps.exams.grading import (
    close_if_expired,
    finish_attempt,
    has_passed,
    options_for,
    save_answer,
    start_attempt,
)
from apps.exams.models import (
    AttemptStatus,
    Exam,
    ExamAttempt,
    Question,
    QuestionOption,
    QuestionType,
)

User = get_user_model()


class ExamTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره آزمون‌دار",
            slug="exam-course",
            category=cls.category,
            price=1_500_000,
            is_published=True,
        )
        cls.exam = Exam.objects.create(
            course=cls.course,
            title="آزمون پایان دوره",
            time_limit_minutes=30,
            pass_score=70,
            max_attempts=3,
            shuffle_questions=False,
            shuffle_options=False,
            is_published=True,
        )
        cls.questions = [cls.make_question(f"سؤال {index}") for index in range(1, 5)]

        cls.student = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        cls.stranger = User.objects.create_user(
            mobile="09127654321", password="HseTech!2026"
        )

    @classmethod
    def make_question(cls, text, *, points=1, exam=None, correct=True):
        question = Question.objects.create(
            exam=exam or cls.exam, text=text, points=points
        )
        QuestionOption.objects.create(question=question, text="گزینه درست", is_correct=correct, order=0)
        QuestionOption.objects.create(question=question, text="گزینه نادرست", order=1)
        return question

    def correct_option(self, question):
        return question.options.get(is_correct=True)

    def wrong_option(self, question):
        return question.options.filter(is_correct=False).first()

    def answer_all(self, attempt, *, correct=True):
        """به همه سؤال‌های برگه پاسخ می‌دهد."""
        for answer in attempt.answers.select_related("question"):
            option = (
                self.correct_option(answer.question)
                if correct
                else self.wrong_option(answer.question)
            )
            save_answer(attempt, answer, option.pk)


class ExamAccessTests(ExamTestMixin, TestCase):
    """چه کسی به آزمون راه دارد."""

    def test_enrolled_student_can_start(self):
        enroll(self.student, self.course)
        self.assertTrue(check_can_start(self.student, self.exam).allowed)

    def test_stranger_cannot_start(self):
        access = check_can_start(self.stranger, self.exam)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "purchase_required")

    def test_anonymous_cannot_start(self):
        self.assertFalse(check_can_start(AnonymousUser(), self.exam).allowed)

    def test_revoked_enrollment_cannot_start(self):
        enrollment = enroll(self.student, self.course)
        revoke(enrollment)
        self.assertFalse(check_can_start(self.student, self.exam).allowed)

    def test_unpublished_exam_is_hidden_from_students(self):
        enroll(self.student, self.course)
        self.exam.is_published = False
        self.exam.save(update_fields=["is_published"])

        access = check_exam_access(self.student, self.exam)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "exam_unpublished")

    def test_staff_sees_an_unpublished_exam(self):
        staff = User.objects.create_user(mobile="09120000000", is_staff=True)
        self.exam.is_published = False
        self.exam.save(update_fields=["is_published"])

        self.assertTrue(check_exam_access(staff, self.exam).allowed)

    def test_exam_without_questions_cannot_start(self):
        course = Course.objects.create(
            title="دوره بی‌سؤال", slug="empty", category=self.category, is_published=True
        )
        exam = Exam.objects.create(course=course, is_published=True)
        enroll(self.student, course)

        access = check_can_start(self.student, exam)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "exam_empty")

    def test_attempt_limit_is_enforced(self):
        enroll(self.student, self.course)
        for _ in range(3):
            finish_attempt(start_attempt(self.student, self.exam))

        self.assertEqual(attempts_left(self.student, self.exam), 0)
        access = check_can_start(self.student, self.exam)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "attempts_exhausted")

    def test_unlimited_attempts_when_max_is_zero(self):
        enroll(self.student, self.course)
        self.exam.max_attempts = 0
        self.exam.save(update_fields=["max_attempts"])

        self.assertIsNone(attempts_left(self.student, self.exam))

    def test_course_completion_can_be_required(self):
        enroll(self.student, self.course)
        section = Section.objects.create(course=self.course, title="فصل")
        Lesson.objects.create(section=section, title="درس")

        self.exam.require_course_completion = True
        self.exam.save(update_fields=["require_course_completion"])

        access = check_can_start(self.student, self.exam)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "course_not_completed")


class AttemptSheetTests(ExamTestMixin, TestCase):
    """برگه امتحان در لحظه شروع قفل می‌شود."""

    def setUp(self):
        enroll(self.student, self.course)

    def test_sheet_is_built_at_start(self):
        attempt = start_attempt(self.student, self.exam)
        self.assertEqual(attempt.answers.count(), 4)
        self.assertEqual(attempt.total_points, 4)

    def test_question_count_limits_the_sheet(self):
        self.exam.question_count = 2
        self.exam.save(update_fields=["question_count"])

        attempt = start_attempt(self.student, self.exam)
        self.assertEqual(attempt.answers.count(), 2)

    def test_adding_a_question_does_not_change_a_running_sheet(self):
        attempt = start_attempt(self.student, self.exam)
        self.make_question("سؤال تازه")

        self.assertEqual(attempt.answers.count(), 4)

    def test_inactive_questions_stay_out(self):
        self.questions[0].is_active = False
        self.questions[0].save(update_fields=["is_active"])

        attempt = start_attempt(self.student, self.exam)
        self.assertEqual(attempt.answers.count(), 3)

    def test_question_without_a_correct_option_stays_out(self):
        broken = Question.objects.create(exam=self.exam, text="سؤال ناقص")
        QuestionOption.objects.create(question=broken, text="فقط یک گزینه")

        attempt = start_attempt(self.student, self.exam)
        self.assertNotIn(broken.pk, attempt.answers.values_list("question_id", flat=True))

    def test_option_order_is_stable_across_reloads(self):
        """ترتیب تصادفی گزینه‌ها نباید با هر بار تازه‌کردن صفحه عوض شود."""
        self.exam.shuffle_options = True
        self.exam.save(update_fields=["shuffle_options"])
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.first()

        first = [option.pk for option in options_for(answer, True)]
        second = [option.pk for option in options_for(answer, True)]

        self.assertEqual(first, second)

    def test_deadline_is_stored_at_start(self):
        attempt = start_attempt(self.student, self.exam)
        self.assertIsNotNone(attempt.expires_at)

        # تغییر مدت آزمون، مهلت کسی که مشغول است را جابه‌جا نمی‌کند.
        expires_at = attempt.expires_at
        self.exam.time_limit_minutes = 5
        self.exam.save(update_fields=["time_limit_minutes"])
        attempt.refresh_from_db()

        self.assertEqual(attempt.expires_at, expires_at)

    def test_exam_without_a_time_limit_has_no_deadline(self):
        self.exam.time_limit_minutes = 0
        self.exam.save(update_fields=["time_limit_minutes"])

        attempt = start_attempt(self.student, self.exam)
        self.assertIsNone(attempt.expires_at)
        self.assertIsNone(attempt.remaining_seconds)


class GradingTests(ExamTestMixin, TestCase):
    """تصحیح خودکار و نمره."""

    def setUp(self):
        enroll(self.student, self.course)
        self.attempt = start_attempt(self.student, self.exam)

    def test_all_correct_is_full_score(self):
        self.answer_all(self.attempt, correct=True)
        finish_attempt(self.attempt)

        self.assertEqual(self.attempt.score, 100)
        self.assertTrue(self.attempt.is_passed)
        self.assertEqual(self.attempt.earned_points, 4)

    def test_all_wrong_is_zero(self):
        self.answer_all(self.attempt, correct=False)
        finish_attempt(self.attempt)

        self.assertEqual(self.attempt.score, 0)
        self.assertFalse(self.attempt.is_passed)

    def test_unanswered_questions_score_nothing(self):
        answers = list(self.attempt.answers.select_related("question"))
        save_answer(self.attempt, answers[0], self.correct_option(answers[0].question).pk)
        finish_attempt(self.attempt)

        self.assertEqual(self.attempt.score, 25)

    def test_points_are_weighted(self):
        """سؤال با امتیاز بیشتر، سهم بیشتری در نمره دارد."""
        heavy_exam = Exam.objects.create(
            course=Course.objects.create(
                title="دوره وزن‌دار", slug="weighted", category=self.category, is_published=True
            ),
            pass_score=50,
            shuffle_questions=False,
            is_published=True,
        )
        light = self.make_question("سبک", points=1, exam=heavy_exam)
        self.make_question("سنگین", points=3, exam=heavy_exam)
        enroll(self.student, heavy_exam.course)

        attempt = start_attempt(self.student, heavy_exam)
        answer = attempt.answers.get(question=light)
        save_answer(attempt, answer, self.correct_option(light).pk)
        finish_attempt(attempt)

        self.assertEqual(attempt.score, 25)

    def test_pass_score_boundary_is_inclusive(self):
        self.exam.pass_score = 75
        self.exam.save(update_fields=["pass_score"])
        attempt = start_attempt(self.student, self.exam)

        answers = list(attempt.answers.select_related("question"))
        for answer in answers[:3]:
            save_answer(attempt, answer, self.correct_option(answer.question).pk)
        finish_attempt(attempt)

        self.assertEqual(attempt.score, 75)
        self.assertTrue(attempt.is_passed)

    def test_result_does_not_change_when_the_exam_changes_later(self):
        """قاعده اصلی: کارنامه ثبت‌شده، تاریخ است و بازنویسی نمی‌شود."""
        self.answer_all(self.attempt, correct=True)
        finish_attempt(self.attempt)

        self.exam.pass_score = 100
        self.exam.save(update_fields=["pass_score"])
        self.questions[0].points = 10
        self.questions[0].save(update_fields=["points"])

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 100)
        self.assertEqual(self.attempt.total_points, 4)
        self.assertEqual(self.attempt.pass_score, 70)
        self.assertTrue(self.attempt.is_passed)

    def test_finishing_twice_keeps_the_first_result(self):
        self.answer_all(self.attempt, correct=True)
        finish_attempt(self.attempt)
        finished_at = self.attempt.finished_at

        self.answer_all(self.attempt, correct=False)
        finish_attempt(self.attempt)

        self.assertEqual(self.attempt.score, 100)
        self.assertEqual(self.attempt.finished_at, finished_at)

    def test_has_passed_uses_the_best_attempt(self):
        self.answer_all(self.attempt, correct=False)
        finish_attempt(self.attempt)
        self.assertFalse(has_passed(self.student, self.exam))

        second = start_attempt(self.student, self.exam)
        self.answer_all(second, correct=True)
        finish_attempt(second)

        self.assertTrue(has_passed(self.student, self.exam))


class DeadlineTests(ExamTestMixin, TestCase):
    """مهلت آزمون را سرور اجرا می‌کند."""

    def setUp(self):
        enroll(self.student, self.course)
        self.attempt = start_attempt(self.student, self.exam)

    def expire(self, minutes_ago=5):
        self.attempt.expires_at = timezone.now() - timedelta(minutes=minutes_ago)
        self.attempt.save(update_fields=["expires_at"])

    def test_answer_after_the_deadline_is_rejected(self):
        answer = self.attempt.answers.select_related("question").first()
        self.expire()

        saved = save_answer(self.attempt, answer, self.correct_option(answer.question).pk)

        self.assertFalse(saved)
        answer.refresh_from_db()
        self.assertIsNone(answer.selected_option)

    def test_a_submit_a_few_seconds_late_is_still_accepted(self):
        """ثبت نهایی چند ثانیه در راه است؛ نباید دور ریخته شود."""
        answer = self.attempt.answers.select_related("question").first()
        self.attempt.expires_at = timezone.now() - timedelta(seconds=10)
        self.attempt.save(update_fields=["expires_at"])

        self.assertTrue(
            save_answer(self.attempt, answer, self.correct_option(answer.question).pk)
        )

    def test_expired_attempt_is_graded_from_saved_answers(self):
        answers = list(self.attempt.answers.select_related("question"))
        save_answer(self.attempt, answers[0], self.correct_option(answers[0].question).pk)
        self.expire()

        self.assertTrue(close_if_expired(self.attempt))
        self.assertEqual(self.attempt.status, AttemptStatus.FINISHED)
        self.assertTrue(self.attempt.auto_submitted)
        self.assertEqual(self.attempt.score, 25)

    def test_an_option_from_another_question_is_refused(self):
        answers = list(self.attempt.answers.select_related("question"))
        foreign = self.correct_option(answers[1].question)

        self.assertFalse(save_answer(self.attempt, answers[0], foreign.pk))


class ExamViewTests(ExamTestMixin, TestCase):
    """صفحه‌های آزمون."""

    def setUp(self):
        enroll(self.student, self.course)
        self.detail_url = reverse("exams:detail", kwargs={"slug": self.course.slug})
        self.start_url = reverse("exams:start", kwargs={"slug": self.course.slug})

    def test_detail_page_shows_the_rules(self):
        self.client.force_login(self.student)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "قوانین این آزمون")
        self.assertContains(response, "شروع آزمون")

    def test_detail_page_tells_a_stranger_why_it_is_closed(self):
        self.client.force_login(self.stranger)
        response = self.client.get(self.detail_url)

        self.assertContains(response, "ثبت‌نام")
        self.assertNotContains(response, "شروع آزمون")

    def test_unpublished_exam_is_404_for_students(self):
        self.exam.is_published = False
        self.exam.save(update_fields=["is_published"])
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_start_requires_post(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.start_url).status_code, 405)

    def test_start_creates_one_attempt_and_opens_the_sheet(self):
        self.client.force_login(self.student)
        response = self.client.post(self.start_url)

        attempt = ExamAttempt.objects.get(user=self.student, exam=self.exam)
        self.assertRedirects(response, reverse("exams:take", kwargs={"pk": attempt.pk}))

    def test_starting_twice_continues_the_same_attempt(self):
        """دکمه شروع نباید با هر بار زدن، یکی از دفعات مجاز را بسوزاند."""
        self.client.force_login(self.student)
        self.client.post(self.start_url)
        self.client.post(self.start_url)

        self.assertEqual(ExamAttempt.objects.filter(user=self.student).count(), 1)

    def test_stranger_cannot_start(self):
        self.client.force_login(self.stranger)
        self.client.post(self.start_url)

        self.assertFalse(ExamAttempt.objects.filter(user=self.stranger).exists())

    def test_taking_someone_elses_attempt_is_404(self):
        attempt = start_attempt(self.student, self.exam)
        self.client.force_login(self.stranger)

        url = reverse("exams:take", kwargs={"pk": attempt.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_submitting_the_form_grades_the_attempt(self):
        attempt = start_attempt(self.student, self.exam)
        self.client.force_login(self.student)

        payload = {
            f"question_{answer.pk}": self.correct_option(answer.question).pk
            for answer in attempt.answers.select_related("question")
        }
        response = self.client.post(
            reverse("exams:take", kwargs={"pk": attempt.pk}), payload
        )

        attempt.refresh_from_db()
        self.assertRedirects(response, attempt.get_absolute_url())
        self.assertEqual(attempt.score, 100)

    def test_opening_an_expired_attempt_closes_it(self):
        attempt = start_attempt(self.student, self.exam)
        attempt.expires_at = timezone.now() - timedelta(minutes=1)
        attempt.save(update_fields=["expires_at"])
        self.client.force_login(self.student)

        response = self.client.get(reverse("exams:take", kwargs={"pk": attempt.pk}))

        attempt.refresh_from_db()
        self.assertRedirects(response, attempt.get_absolute_url())
        self.assertTrue(attempt.auto_submitted)

    def test_result_page_shows_the_score(self):
        attempt = start_attempt(self.student, self.exam)
        self.answer_all(attempt, correct=True)
        finish_attempt(attempt)
        self.client.force_login(self.student)

        response = self.client.get(attempt.get_absolute_url())

        self.assertContains(response, "قبول شدید")
        self.assertContains(response, "مرور پاسخ‌ها")

    def test_result_page_hides_answers_when_the_exam_says_so(self):
        self.exam.show_correct_answers = False
        self.exam.save(update_fields=["show_correct_answers"])
        attempt = start_attempt(self.student, self.exam)
        finish_attempt(attempt)
        self.client.force_login(self.student)

        response = self.client.get(attempt.get_absolute_url())

        self.assertNotContains(response, "مرور پاسخ‌ها")

    def test_autosave_endpoint_saves_one_answer(self):
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.select_related("question").first()
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("exams:answer", kwargs={"pk": attempt.pk}),
            {"answer": answer.pk, "option": self.correct_option(answer.question).pk},
        )

        answer.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(answer.selected_option)

    def test_autosave_is_refused_after_the_deadline(self):
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.select_related("question").first()
        attempt.expires_at = timezone.now() - timedelta(minutes=5)
        attempt.save(update_fields=["expires_at"])
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("exams:answer", kwargs={"pk": attempt.pk}),
            {"answer": answer.pk, "option": self.correct_option(answer.question).pk},
        )

        self.assertEqual(response.status_code, 400)

    def test_my_exams_page_requires_login(self):
        response = self.client.get(reverse("exams:my"))
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_my_exams_page_lists_only_my_attempts(self):
        mine = start_attempt(self.student, self.exam)
        finish_attempt(mine)
        enroll(self.stranger, self.course)
        finish_attempt(start_attempt(self.stranger, self.exam))

        self.client.force_login(self.student)
        response = self.client.get(reverse("exams:my"))

        self.assertEqual(len(response.context["attempts"]), 1)


class QuestionModelTests(ExamTestMixin, TestCase):
    def test_essay_questions_are_refused_for_now(self):
        from django.core.exceptions import ValidationError

        question = Question(
            exam=self.exam, text="تشریح کنید", question_type=QuestionType.ESSAY
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_answered_question_cannot_be_deleted(self):
        """پاک‌کردن سؤالِ پاسخ‌داده‌شده، کارنامه را ناقص می‌کند."""
        from django.db.models import ProtectedError

        enroll(self.student, self.course)
        attempt = start_attempt(self.student, self.exam)
        answer = attempt.answers.select_related("question").first()
        save_answer(attempt, answer, self.correct_option(answer.question).pk)

        with self.assertRaises(ProtectedError):
            answer.question.delete()
