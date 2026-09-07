"""آدرس‌های سبد خرید و سفارش‌ها."""

from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<uslug:slug>/", views.cart_add, name="cart_add"),
    path("cart/remove/<uslug:slug>/", views.cart_remove, name="cart_remove"),
    path("cart/coupon/", views.coupon_apply, name="coupon_apply"),
    path("cart/coupon/remove/", views.coupon_remove, name="coupon_remove"),
    path("checkout/", views.checkout_view, name="checkout"),
    path("orders/", views.order_list, name="list"),
    path("orders/<str:order_number>/", views.order_detail, name="detail"),
    path("orders/<str:order_number>/cancel/", views.order_cancel, name="cancel"),
]
