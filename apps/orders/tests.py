"""
تست‌های فاز ۱۱ — سبد خرید، کد تخفیف و سفارش.

حساس‌ترین بخش این فاز پول است. تست‌ها روی سه چیز تمرکز دارند:
۱. هیچ مبلغی از سمت مرورگر پذیرفته نشود.
۲. فاکتور ثبت‌شده با گذشت زمان و تغییر قیمت‌ها عوض نشود.
۳. کسی نتواند سفارش دیگری را ببیند یا تغییر دهد.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Course, CourseCategory
from apps.orders.models import Coupon, DiscountType, Order, OrderItem, OrderStatus
from apps.orders.services import (
    check_coupon,
    create_order,
    mark_order_paid,
    purchased_course_ids,
)

User = get_user_model()


class OrderTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")

        cls.course_a = Course.objects.create(
            title="دوره الف",
            slug="course-a",
            category=cls.category,
            price=1_000_000,
            is_published=True,
        )
        cls.course_b = Course.objects.create(
            title="دوره ب",
            slug="course-b",
            category=cls.category,
            price=2_000_000,
            discount_price=1_500_000,
            is_published=True,
        )
        cls.free_course = Course.objects.create(
            title="دوره رایگان",
            slug="free-course",
            category=cls.category,
            price=0,
            is_published=True,
        )
        cls.draft = Course.objects.create(
            title="دوره پیش‌نویس",
            slug="draft",
            category=cls.category,
            price=500_000,
            is_published=False,
        )

        cls.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")
        cls.other = User.objects.create_user(mobile="09127654321", password="HseTech!2026")


class CartTests(OrderTestMixin, TestCase):
    def setUp(self):
        self.cart_url = reverse("orders:cart")

    def _add(self, course):
        return self.client.post(reverse("orders:cart_add", args=[course.slug]))

    def test_adding_a_course_to_the_cart(self):
        self._add(self.course_a)

        response = self.client.get(self.cart_url)
        self.assertContains(response, "دوره الف")
        self.assertEqual(response.context["subtotal"], 1_000_000)

    def test_a_guest_can_use_the_cart(self):
        """سبد باید قبل از ورود هم کار کند؛ وگرنه کاربر تازه‌وارد را می‌پرانیم."""
        self._add(self.course_a)
        self.assertEqual(self.client.get(self.cart_url).context["subtotal"], 1_000_000)

    def test_adding_the_same_course_twice_does_not_duplicate_it(self):
        self._add(self.course_a)
        self._add(self.course_a)

        self.assertEqual(len(self.client.get(self.cart_url).context["lines"]), 1)

    def test_cart_uses_the_discounted_price(self):
        self._add(self.course_b)

        self.assertEqual(self.client.get(self.cart_url).context["subtotal"], 1_500_000)

    def test_unpublished_course_cannot_be_added(self):
        response = self.client.post(reverse("orders:cart_add", args=[self.draft.slug]))
        self.assertEqual(response.status_code, 404)

    def test_removing_a_course(self):
        self._add(self.course_a)
        self.client.post(reverse("orders:cart_remove", args=[self.course_a.slug]))

        self.assertEqual(self.client.get(self.cart_url).context["lines"], [])

    def test_adding_with_get_is_rejected(self):
        """
        اگر افزودن به سبد با GET کار می‌کرد، یک تصویر در سایتی دیگر
        می‌توانست بی‌اجازه سبد کاربر را پر کند.
        """
        url = reverse("orders:cart_add", args=[self.course_a.slug])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_a_course_that_becomes_unpublished_drops_out_of_the_cart(self):
        self._add(self.course_a)

        self.course_a.is_published = False
        self.course_a.save()

        response = self.client.get(self.cart_url)
        self.assertEqual(response.context["lines"], [])
        self.assertEqual(response.context["subtotal"], 0)

    def test_the_cart_only_stores_ids_not_prices(self):
        """
        اگر قیمت در Session ذخیره می‌شد، کاربر می‌توانست آن را دستکاری کند
        و دوره گران را ارزان بخرد. Session فقط شناسه دوره را نگه می‌دارد.
        """
        self._add(self.course_a)
        stored = self.client.session["cart"]

        self.assertEqual(stored, [self.course_a.pk])

    def test_the_header_shows_how_many_items_are_in_the_cart(self):
        self._add(self.course_a)
        self._add(self.course_b)

        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["cart_count"], 2)

    def test_a_closed_course_cannot_be_added(self):
        self.course_a.start_date = timezone.now().date() - timedelta(days=10)
        self.course_a.save()

        self._add(self.course_a)
        self.assertEqual(self.client.get(self.cart_url).context["lines"], [])


class CouponRuleTests(OrderTestMixin, TestCase):
    def _check(self, coupon_code, subtotal=1_000_000, courses=None, user=None):
        return check_coupon(
            coupon_code,
            user=user or self.user,
            courses=courses if courses is not None else [self.course_a],
            subtotal=subtotal,
        )

    def test_percentage_discount(self):
        Coupon.objects.create(code="OFF20", discount_type=DiscountType.PERCENT, value=20)

        result = self._check("OFF20")
        self.assertTrue(result.valid)
        self.assertEqual(result.discount, 200_000)

    def test_fixed_discount(self):
        Coupon.objects.create(code="MINUS", discount_type=DiscountType.FIXED, value=300_000)

        self.assertEqual(self._check("MINUS").discount, 300_000)

    def test_discount_never_exceeds_the_order_total(self):
        """
        بدون این محدودیت، تخفیف ثابتِ بزرگ‌تر از سبد، جمع فاکتور را منفی
        می‌کرد و سایت به کاربر بدهکار می‌شد.
        """
        Coupon.objects.create(code="HUGE", discount_type=DiscountType.FIXED, value=9_000_000)

        self.assertEqual(self._check("HUGE", subtotal=1_000_000).discount, 1_000_000)

    def test_percentage_discount_respects_its_cap(self):
        Coupon.objects.create(
            code="CAPPED",
            discount_type=DiscountType.PERCENT,
            value=50,
            max_discount_amount=200_000,
        )

        self.assertEqual(self._check("CAPPED", subtotal=1_000_000).discount, 200_000)

    def test_code_is_case_insensitive(self):
        Coupon.objects.create(code="NOWRUZ", value=10)

        self.assertTrue(self._check("nowruz").valid)
        self.assertTrue(self._check("  NoWrUz  ").valid)

    def test_unknown_code_is_rejected(self):
        result = self._check("DOES-NOT-EXIST")

        self.assertFalse(result.valid)
        self.assertIn("معتبر نیست", result.message)

    def test_inactive_code_is_rejected(self):
        Coupon.objects.create(code="OFF", value=10, is_active=False)

        self.assertFalse(self._check("OFF").valid)

    def test_expired_code_is_rejected(self):
        Coupon.objects.create(
            code="OLD", value=10, valid_until=timezone.now() - timedelta(days=1)
        )

        result = self._check("OLD")
        self.assertFalse(result.valid)
        self.assertIn("مهلت", result.message)

    def test_code_that_has_not_started_yet_is_rejected(self):
        Coupon.objects.create(
            code="SOON", value=10, valid_from=timezone.now() + timedelta(days=1)
        )

        self.assertFalse(self._check("SOON").valid)

    def test_exhausted_code_is_rejected(self):
        Coupon.objects.create(code="LIMITED", value=10, max_uses=5, used_count=5)

        result = self._check("LIMITED")
        self.assertFalse(result.valid)
        self.assertIn("ظرفیت", result.message)

    def test_minimum_order_amount_is_enforced(self):
        Coupon.objects.create(code="BIGONLY", value=10, min_order_amount=5_000_000)

        self.assertFalse(self._check("BIGONLY", subtotal=1_000_000).valid)

    def test_code_restricted_to_other_courses_is_rejected(self):
        coupon = Coupon.objects.create(code="BONLY", value=10)
        coupon.courses.add(self.course_b)

        self.assertFalse(self._check("BONLY", courses=[self.course_a]).valid)
        self.assertTrue(self._check("BONLY", courses=[self.course_b]).valid)

    def test_per_user_limit_counts_only_paid_orders(self):
        """
        سفارشی که کاربر رها کرده نباید سهمیه او را بسوزاند؛ وگرنه کسی که
        وسط پرداخت منصرف شده، دیگر هرگز نمی‌تواند از کد استفاده کند.
        """
        coupon = Coupon.objects.create(code="ONCE", value=10, per_user_limit=1)

        abandoned = Order.objects.create(user=self.user, coupon=coupon)
        self.assertTrue(self._check("ONCE").valid)

        abandoned.status = OrderStatus.PAID
        abandoned.save()
        self.assertFalse(self._check("ONCE").valid)


class CouponViewTests(OrderTestMixin, TestCase):
    def setUp(self):
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))
        Coupon.objects.create(code="OFF20", value=20)

    def test_applying_a_coupon_updates_the_total(self):
        self.client.post(reverse("orders:coupon_apply"), {"code": "OFF20"})

        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.context["discount"], 200_000)
        self.assertEqual(response.context["total"], 800_000)

    def test_only_the_code_is_stored_in_the_session_not_the_amount(self):
        """
        اگر مبلغ تخفیف در Session بود، کاربر می‌توانست آن را عوض کند.
        فقط متن کد ذخیره می‌شود و مبلغ هربار در سرور حساب می‌شود.
        """
        self.client.post(reverse("orders:coupon_apply"), {"code": "OFF20"})

        self.assertEqual(self.client.session["coupon_code"], "OFF20")
        self.assertNotIn("discount", self.client.session)

    def test_removing_a_coupon(self):
        self.client.post(reverse("orders:coupon_apply"), {"code": "OFF20"})
        self.client.post(reverse("orders:coupon_remove"))

        self.assertEqual(self.client.get(reverse("orders:cart")).context["discount"], 0)

    def test_a_coupon_that_expires_later_stops_applying(self):
        self.client.post(reverse("orders:coupon_apply"), {"code": "OFF20"})

        Coupon.objects.filter(code="OFF20").update(is_active=False)

        response = self.client.get(reverse("orders:cart"))
        self.assertEqual(response.context["discount"], 0)
        self.assertEqual(response.context["total"], 1_000_000)


class CheckoutTests(OrderTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))
        self.client.post(reverse("orders:cart_add", args=[self.course_b.slug]))
        self.url = reverse("orders:checkout")

    def test_checkout_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_an_empty_cart_redirects_away(self):
        self.client.post(reverse("orders:cart_remove", args=[self.course_a.slug]))
        self.client.post(reverse("orders:cart_remove", args=[self.course_b.slug]))

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("courses:list"))

    def test_placing_an_order_creates_it_with_its_items(self):
        self.client.post(self.url)

        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.item_count, 2)
        self.assertEqual(order.subtotal, 2_500_000)
        self.assertEqual(order.total, 2_500_000)

    def test_a_new_order_is_not_paid(self):
        """
        ثبت سفارش با پرداخت یکی نیست. تنها راه رسیدن به وضعیت «پرداخت شده»
        تأیید سمت سرورِ درگاه است (فاز ۱۲).
        """
        self.client.post(self.url)

        self.assertEqual(Order.objects.get().status, OrderStatus.PENDING)
        self.assertIsNone(Order.objects.get().paid_at)

    def test_the_cart_is_emptied_after_ordering(self):
        self.client.post(self.url)

        self.assertEqual(self.client.session.get("cart", []), [])

    def test_prices_sent_by_the_browser_are_ignored(self):
        """
        مهم‌ترین تست این فاز: هرچه کاربر در فرم بفرستد، مبلغ از دیتابیس
        خوانده می‌شود.
        """
        self.client.post(self.url, {"total": "1000", "subtotal": "1000", "price": "1"})

        self.assertEqual(Order.objects.get().total, 2_500_000)

    def test_the_coupon_is_applied_to_the_order(self):
        Coupon.objects.create(code="OFF20", value=20)
        self.client.post(reverse("orders:coupon_apply"), {"code": "OFF20"})

        self.client.post(self.url)

        order = Order.objects.get()
        self.assertEqual(order.discount_amount, 500_000)
        self.assertEqual(order.total, 2_000_000)
        self.assertEqual(order.coupon_code, "OFF20")

    def test_an_already_purchased_course_is_removed_from_the_cart(self):
        paid = create_order(user=self.user, lines=[])
        OrderItem.objects.create(
            order=paid,
            course=self.course_a,
            title=self.course_a.title,
            unit_price=self.course_a.price,
            final_price=self.course_a.final_price,
        )
        mark_order_paid(paid)

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertNotIn(self.course_a.pk, self.client.session["cart"])

    def test_order_numbers_are_unique(self):
        self.client.post(self.url)
        self.client.post(reverse("orders:cart_add", args=[self.free_course.slug]))
        self.client.post(self.url)

        numbers = set(Order.objects.values_list("order_number", flat=True))
        self.assertEqual(len(numbers), 2)


class OrderSnapshotTests(OrderTestMixin, TestCase):
    """فاکتور ثبت‌شده نباید با تغییر بعدی دوره عوض شود."""

    def setUp(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))
        self.client.post(reverse("orders:checkout"))
        self.order = Order.objects.get()

    def test_a_later_price_increase_does_not_change_the_invoice(self):
        self.course_a.price = 9_000_000
        self.course_a.save()

        self.order.refresh_from_db()
        self.assertEqual(self.order.total, 1_000_000)
        self.assertEqual(self.order.items.get().final_price, 1_000_000)

    def test_renaming_a_course_does_not_change_the_invoice(self):
        self.course_a.title = "عنوان کاملاً جدید"
        self.course_a.save()

        self.assertEqual(self.order.items.get().title, "دوره الف")

    def test_a_sold_course_cannot_be_deleted(self):
        """حذف دوره فروخته‌شده، فاکتورهای پرداخت‌شده را بی‌معنا می‌کرد."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.course_a.delete()


class OrderAccessTests(OrderTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))
        self.client.post(reverse("orders:checkout"))
        self.order = Order.objects.get()

    def test_a_user_sees_their_own_order(self):
        response = self.client.get(self.order.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

    def test_another_user_cannot_open_it(self):
        """
        بدون فیلتر روی کاربر، هرکسی با داشتن شماره سفارش می‌توانست فاکتور
        و شماره تماس دیگری را ببیند.
        """
        self.client.force_login(self.other)

        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 404)

    def test_a_guest_is_sent_to_the_login_page(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.order.get_absolute_url()).status_code, 302)

    def test_the_order_list_shows_only_your_own_orders(self):
        self.client.force_login(self.other)

        self.assertEqual(len(self.client.get(reverse("orders:list")).context["orders"]), 0)

    def test_canceling_an_unpaid_order(self):
        self.client.post(reverse("orders:cancel", args=[self.order.order_number]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELED)

    def test_a_paid_order_cannot_be_canceled(self):
        mark_order_paid(self.order)

        self.client.post(reverse("orders:cancel", args=[self.order.order_number]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)

    def test_another_user_cannot_cancel_your_order(self):
        self.client.force_login(self.other)
        self.client.post(reverse("orders:cancel", args=[self.order.order_number]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_canceling_with_get_is_rejected(self):
        url = reverse("orders:cancel", args=[self.order.order_number])
        self.assertEqual(self.client.get(url).status_code, 405)


class PaymentMarkingTests(OrderTestMixin, TestCase):
    def setUp(self):
        self.order = create_order(user=self.user, lines=[])

    def test_marking_paid_sets_the_time(self):
        mark_order_paid(self.order)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertIsNotNone(self.order.paid_at)

    def test_marking_paid_twice_does_not_double_count_the_coupon(self):
        coupon = Coupon.objects.create(code="OFF", value=10)
        self.order.coupon = coupon
        self.order.save()

        mark_order_paid(self.order)
        mark_order_paid(self.order)

        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_paying_records_the_course_as_purchased(self):
        OrderItem.objects.create(
            order=self.order,
            course=self.course_a,
            title=self.course_a.title,
            unit_price=self.course_a.price,
            final_price=self.course_a.final_price,
        )

        self.assertEqual(purchased_course_ids(self.user), set())

        mark_order_paid(self.order)
        self.assertEqual(purchased_course_ids(self.user), {self.course_a.pk})

    def test_an_unpaid_order_does_not_count_as_a_purchase(self):
        OrderItem.objects.create(
            order=self.order,
            course=self.course_a,
            title=self.course_a.title,
            unit_price=self.course_a.price,
            final_price=self.course_a.final_price,
        )

        self.assertEqual(purchased_course_ids(self.user), set())


class CoursePageCartTests(OrderTestMixin, TestCase):
    def test_the_course_page_offers_to_add_to_the_cart(self):
        response = self.client.get(self.course_a.get_absolute_url())

        self.assertContains(response, "افزودن به سبد خرید")
        self.assertFalse(response.context["in_cart"])

    def test_the_button_changes_once_the_course_is_in_the_cart(self):
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))

        response = self.client.get(self.course_a.get_absolute_url())
        self.assertTrue(response.context["in_cart"])
        self.assertContains(response, "در سبد خرید")

    def test_a_purchased_course_shows_a_continue_button_instead(self):
        self.client.force_login(self.user)
        order = create_order(user=self.user, lines=[])
        OrderItem.objects.create(
            order=order,
            course=self.course_a,
            title=self.course_a.title,
            unit_price=self.course_a.price,
            final_price=self.course_a.final_price,
        )
        mark_order_paid(order)

        response = self.client.get(self.course_a.get_absolute_url())
        # از فاز ۱۴، پیام از روی ثبت‌نام می‌آید نه از روی سفارش
        self.assertContains(response, "شما در این دوره ثبت‌نام کرده‌اید")
        self.assertNotContains(response, "افزودن به سبد خرید")


class PersianNumberFormattingTests(OrderTestMixin, TestCase):
    """
    اعداد داخل پیام‌های فارسی باید با ارقام فارسی نوشته شوند.

    این را در مرورگر دیدم: وسط جمله فارسی یک «1,420,000» انگلیسی نشسته
    بود در حالی که همان عدد در جدول کنارش فارسی بود.
    """

    def test_the_coupon_message_uses_persian_digits(self):
        Coupon.objects.create(code="OFF20", value=20)
        self.client.post(reverse("orders:cart_add", args=[self.course_a.slug]))

        response = self.client.post(
            reverse("orders:coupon_apply"), {"code": "OFF20"}, follow=True
        )
        body = response.content.decode()

        self.assertIn("۲۰۰,۰۰۰ تومان تخفیف گرفتید", body)
        self.assertNotIn("200,000 تومان تخفیف", body)

    def test_the_minimum_amount_message_uses_persian_digits(self):
        Coupon.objects.create(code="BIGONLY", value=10, min_order_amount=5_000_000)

        result = check_coupon(
            "BIGONLY", user=self.user, courses=[self.course_a], subtotal=1_000_000
        )
        self.assertIn("۵,۰۰۰,۰۰۰", result.message)
