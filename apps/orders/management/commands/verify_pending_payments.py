"""
رسیدگی به تراکنش‌های در انتظار.

یک پرداخت در دو حالت ممکن است «در انتظار» بماند، و هر دو را باید کسی
ببیند — نه اینکه تا ابد همان‌طور بمانند:

**۱. نامعلوم** — verify را فرستادیم و پاسخش در شبکه گم شد. شاید درگاه
تأیید کرده و پول کسر شده، شاید نه. این یکی **حیاتی است**: اگر تأیید شده
باشد و ما هیچ‌وقت نفهمیم، مشتری پول داده و دوره‌اش باز نشده — و چون
تأیید شده، شاپرک هم خودکار برش نمی‌گرداند. این دستور دوباره می‌پرسد؛
زرین‌پال برای تراکنشی که قبلاً تأیید شده کد 101 برمی‌گرداند و دسترسی باز
می‌شود.

**۲. رهاشده** — کاربر به درگاه رفت و دیگر برنگشت. اگر مهلت تمام شده باشد،
«ناموفق — منقضی» ثبت می‌شود **بدون تماس با درگاه**؛ اگر مبلغی کسر شده،
چون verify نشده، شاپرک خودکار برمی‌گرداند.

**آنچه عمداً دست نمی‌خورد:** تراکنشی که هنوز در مهلت است و verify نشده.
ممکن است کاربر همین حالا روی صفحه بانک باشد؛ پرسیدن از درگاه در این لحظه
جواب «پرداخت نشده» می‌دهد و تراکنشی را که چند ثانیه بعد پرداخت می‌شد،
ناموفق ثبت می‌کند.

اجرا (سرور، هر ده دقیقه — deploy/hse-verify-payments.timer):
    python manage.py verify_pending_payments
    python manage.py verify_pending_payments --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.orders.models import Payment, PaymentStatus
from apps.orders.services import verify_payment


class Command(BaseCommand):
    help = "تأیید دوباره تراکنش‌های نامعلوم و بستن تراکنش‌های رهاشده"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="فقط نشان بده چه کاری انجام می‌شد؛ چیزی تغییر نکند",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        pending = (
            Payment.objects.filter(status=PaymentStatus.PENDING)
            .exclude(authority="")
            .select_related("order", "order__user")
            .order_by("created_at")
        )

        counts = {"verified": 0, "failed": 0, "uncertain": 0, "skipped": 0}

        for payment in pending:
            asked_before = bool(payment.raw_response.get("verify_attempts"))

            if not asked_before and not payment.is_expired():
                # ممکن است کاربر همین حالا روی صفحه بانک باشد.
                counts["skipped"] += 1
                continue

            label = "نامعلوم" if asked_before else "منقضی"

            if dry_run:
                self.stdout.write(
                    f"  [آزمایشی] {payment.order.order_number}  ({label})"
                )
                continue

            result = verify_payment(payment, {})
            payment.refresh_from_db()

            if payment.status == PaymentStatus.SUCCESS:
                counts["verified"] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {payment.order.order_number}  تأیید شد  "
                        f"(پیگیری {payment.ref_id})"
                    )
                )
            elif result.retryable:
                counts["uncertain"] += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  ? {payment.order.order_number}  هنوز پاسخی از درگاه نیامد"
                    )
                )
            else:
                counts["failed"] += 1
                self.stdout.write(
                    f"  ✗ {payment.order.order_number}  ناموفق ({payment.error_code or '—'})"
                )

        self.stdout.write("")
        self.stdout.write(
            f"تأییدشده: {counts['verified']}  ·  ناموفق: {counts['failed']}  ·  "
            f"هنوز نامعلوم: {counts['uncertain']}  ·  در مهلت (دست نخورد): {counts['skipped']}"
        )

        if counts["uncertain"]:
            self.stdout.write(
                self.style.WARNING(
                    "برخی تراکنش‌ها هنوز نامعلوم‌اند. اجرای بعدی دوباره امتحانشان "
                    "می‌کند؛ اگر چند ساعت ماندند، از پنل زرین‌پال وضعیتشان را ببینید."
                )
            )
