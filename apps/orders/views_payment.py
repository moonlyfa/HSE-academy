"""
Viewهای پرداخت.

سه آدرس دارد:
    /orders/<شماره>/pay/        شروع پرداخت (فقط POST)
    /payments/mock/<شناسه>/     صفحه درگاه آزمایشی (فقط در حالت Mock)
    /payments/callback/         بازگشت از درگاه

نکته‌ای که در هر سه رعایت شده: آدرس بازگشتی درگاه سند پرداخت نیست. فقط
با آن تراکنش را *پیدا* می‌کنیم؛ تأیید واقعی را سرویس پرداخت با تماس
سرور به سرور انجام می‌دهد.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Order, Payment, PaymentStatus
from .services import start_payment, verify_payment

logger = logging.getLogger("hse.payment")


@login_required
@require_POST
def payment_start(request: HttpRequest, order_number: str) -> HttpResponse:
    """
    شروع پرداخت یک سفارش.

    فیلتر روی user حیاتی است: بدون آن، هرکسی با داشتن شماره سفارش دیگری
    می‌توانست برای سفارش او تراکنش بسازد.
    """
    order = get_object_or_404(Order, order_number=order_number, user=request.user)

    callback_url = request.build_absolute_uri(reverse("orders:payment_callback"))
    result = start_payment(order, callback_url)

    if not result.success:
        messages.error(request, result.message or "شروع پرداخت ممکن نشد.")
        return redirect(order.get_absolute_url())

    return redirect(result.redirect_url)


def mock_gateway(request: HttpRequest, authority: str) -> HttpResponse:
    """
    صفحه درگاه آزمایشی.

    این صفحه جای بانک را می‌گیرد. با POST، تصمیم کاربر (موفق یا ناموفق)
    **در دیتابیس** ذخیره می‌شود و بعد به آدرس بازگشتی می‌رویم. متد verify
    همان مقدار ذخیره‌شده را می‌خواند، نه پارامتر آدرس را — دقیقاً مثل
    درگاه واقعی که سرور از سرور می‌پرسد.
    """
    if not settings.USE_MOCK_PAYMENT:
        raise Http404("درگاه آزمایشی در این محیط فعال نیست.")

    payment = get_object_or_404(
        Payment.objects.select_related("order"), authority=authority
    )

    if not payment.is_pending:
        return redirect(payment.order.get_absolute_url())

    if request.method == "POST":
        decision = "success" if request.POST.get("decision") == "success" else "failed"

        payment.raw_response = {
            **payment.raw_response,
            "mock_decision": decision,
            # شماره پیگیری ساختگی، شبیه چیزی که بانک واقعی می‌دهد
            "mock_ref_id": str(secrets.randbelow(9_000_000_000) + 1_000_000_000),
            "mock_card_pan": "6037",
        }
        payment.save(update_fields=["raw_response", "updated_at"])

        callback = reverse("orders:payment_callback")
        # پارامترها عمداً همان شکل درگاه واقعی هستند تا مسیر بازگشت هم
        # واقعی تست شود — ولی هیچ‌کدام سند پرداخت نیستند.
        status = "OK" if decision == "success" else "NOK"
        return redirect(f"{callback}?Authority={payment.authority}&Status={status}")

    return render(
        request,
        "orders/mock_gateway.html",
        {
            "payment": payment,
            "order": payment.order,
            "forced_result": settings.MOCK_PAYMENT_RESULT,
        },
    )


def payment_callback(request: HttpRequest) -> HttpResponse:
    """
    بازگشت کاربر از درگاه.

    این آدرس را **مرورگر کاربر** صدا می‌زند، نه درگاه. یعنی هر کسی
    می‌تواند دستی بنویسد:

        /payments/callback/?Authority=XYZ&Status=OK

    برای همین Status اصلاً خوانده نمی‌شود. فقط Authority را برمی‌داریم تا
    تراکنش را پیدا کنیم، و بقیه کار را verify_payment انجام می‌دهد که
    خودش از درگاه می‌پرسد.
    """
    authority = (
        request.GET.get("Authority")
        or request.GET.get("authority")
        or ""
    ).strip()

    if not authority:
        messages.error(request, "اطلاعات بازگشت از درگاه ناقص بود.")
        return redirect("orders:list")

    payment = Payment.objects.select_related("order", "order__user").filter(
        authority=authority
    ).first()

    if payment is None:
        logger.warning("بازگشت از درگاه با شناسه ناشناخته: %s", authority[:40])
        messages.error(request, "تراکنش مورد نظر پیدا نشد.")
        return redirect("orders:list")

    result = verify_payment(payment, dict(request.GET.items()))
    payment.refresh_from_db()

    return render(
        request,
        "orders/payment_result.html",
        {
            "payment": payment,
            "order": payment.order,
            "success": result.success,
            "message": result.message,
        },
    )
