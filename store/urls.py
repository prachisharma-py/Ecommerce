from django.urls import path
from django.conf import settings
from django.conf.urls.static import static


from . import views

urlpatterns = [
    path("", views.store, name="store"),    
    path("product/", views.product_list, name="product_list"),
    path("products/<slug:category_slug>/", views.product_list, name="product_list_by_category"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("add_to_cart/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("buy_now/<int:product_id>/", views.buy_now, name="buy_now"),
    path('proceed-to-checkout/', views.proceed_to_checkout, name='proceed_to_checkout'),
    path("checkout/", views.checkout, name="checkout"),
    path('payment-success/',views.payment_success, name='payment_success'),
    path('payment-failed/', views.payment_failed, name='payment_failed'),
    path("signup/", views.signup, name="signup"),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
