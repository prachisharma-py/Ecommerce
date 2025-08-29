from django.shortcuts import render, get_object_or_404, redirect
from .models import Category, Products, Cart, CartItem, Order, OrderItem
from django.contrib.auth import login, logout, authenticate
from .forms import SignUpForm, LoginForm, CheckoutForm
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse
from django.conf import settings
import stripe

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# Create your views here.

def chunk_products(products, chunk_size):
    return [products[i:i + chunk_size] for i in range(0, len(products), chunk_size)]


def store(request):
    categories = Category.objects.all().prefetch_related("products")
    products = list(Products.objects.all()[1:7])
    product_chunks = chunk_products(products, 3) 

    return render(request, "store/store.html", {
        "categories": categories,
        "product_chunks": product_chunks
    })


def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Products.objects.all()
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)
    return render(request, "store/product_list.html", {
        "category": category,
        "categories": categories,
        "products": products
    })


def product_detail(request, slug):
    product = get_object_or_404(Products, slug=slug)
    
    # Default quantity
    quantity = 1

    # Check if 'quantity' is in the session
    if 'quantity' in request.session:
        quantity = request.session['quantity']

    # Handle form submission to adjust quantity
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'increase':
            quantity += 1
        elif action == 'decrease' and quantity > 1:
            quantity -= 1

        # Update the session with the new quantity
        request.session['quantity'] = quantity

    return render(request, "store/product_detail.html", {
        "product": product,
        "quantity": quantity
    })


def cart_detail(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = cart.items.all()

    #Clear Buy Now mode if the user is accessing cart directly
    request.session.pop('buy_now_product_id', None)
    request.session.pop('buy_now_mode', None)

    if request.method == "POST":
        if "remove_item_id" in request.POST:
            # Handle item removal
            item_id = request.POST.get("remove_item_id")
            cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
            cart_item.delete()
        elif "update_item_id" in request.POST:
            # Handle quantity update
            item_id = request.POST.get("update_item_id")
            action = request.POST.get("action")
            cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)

            if action == 'increase':
                cart_item.quantity += 1
            elif action == 'decrease':
                cart_item.quantity = max(1, cart_item.quantity - 1)

            cart_item.total_price = cart_item.product.price * cart_item.quantity
            cart_item.save()
            message = 'Cart Updated!'
            messages.success(request, message)
        
        return redirect('cart_detail')

    for item in cart_items:
        item.total_price = item.product.price * item.quantity
        item.save()

    cart_subtotal = sum(item.total_price for item in cart_items)

    return render(request, "store/cart_detail.html", {
        "cart": cart,
        "cart_items": cart_items,
        "cart_subtotal": cart_subtotal
    })


def add_to_cart(request, product_id):
    product = get_object_or_404(Products, id=product_id)
    quantity = int(request.POST.get('quantity', 1))  

    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    cart_item.quantity = quantity
    cart_item.save()
    
    message = format_html(
        'Product added to cart successfully!<br><a href="{}">View Cart</a>',
        reverse("cart_detail")
    )
    messages.success(request, message)

    # Redirect back to the product detail page
    return redirect('product_detail', slug=product.slug)


def buy_now(request, product_id):
    product = get_object_or_404(Products, id=product_id)
    quantity = int(request.POST.get('quantity', 1))

    cart, _ = Cart.objects.get_or_create(user=request.user)

    cart_item, _ = CartItem.objects.get_or_create(cart=cart, product=product)
    cart_item.quantity = quantity
    cart_item.save()

    
    # Enable buy now mode
    request.session['buy_now_mode'] = True
    request.session['buy_now_product_id'] = product.id

    return redirect('checkout')

    
def checkout(request):
    cart = Cart.objects.filter(user=request.user).first()
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty. Please add items to your cart.")
        return redirect('cart_detail')

    cart_items = cart.items.all() # Check for buy now mode
    buy_now_mode = request.session.get('buy_now_mode', False)
    buy_now_product_id = request.session.get('buy_now_product_id')

    if buy_now_mode and buy_now_product_id:
        cart_items = cart.items.filter(product_id=buy_now_product_id)
    else:
        cart_items = cart.items.all()

    cart_total = sum(item.quantity * item.product.price for item in cart_items)

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.total_amount = cart_total
            order.save()

            # Save order items
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.product.price,
                )

            # Remove only the items that were purchased
            cart_items.delete()

            # Create Stripe Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': 'AniStore Order'},
                        'unit_amount': int(cart_total * 100),  # Convert to cents
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url = f"{request.build_absolute_uri(reverse('payment_success'))}?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=request.build_absolute_uri(reverse('payment_failed')),
            )

            # Store session ID for verification
            order.payment_id = session.id
            order.save()

            return redirect(session.url)
    else:
        form = CheckoutForm()

    context = {
        'cart_items': cart_items,
        'cart_total': cart_total,
        'form': form,
    }
    return render(request, 'store/checkout.html', context)


# Handle successful payment
def payment_success(request):
    session_id = request.GET.get('session_id')
    print("Session ID received:", session_id)

    storage = messages.get_messages(request)
    for _ in storage:
        pass

    if not session_id:
        messages.error(request, "Payment session not found!")
        return redirect('checkout')

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        print("Stripe Session:", session)
    except stripe.error.InvalidRequestError as e:
        print("Stripe Error:", e) 
        messages.error(request, "Invalid or expired session ID.")
        return redirect('checkout')

    try:
        order = Order.objects.get(payment_id=session.id)
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('checkout')

    if session.payment_status == "paid":
        order.payment_status = True
        order.save()

         # Clear cart only after successful payment
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            cart.items.all().delete()

    return render(request, 'store/payment_success.html')


# Handle failed payment
def payment_failed(request):
    return render(request, 'store/payment_failed.html')


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('store')
    else:
        form = SignUpForm()

    return render(request, 'store/signup.html', {
        'form': form
        })


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            # Authenticate the user
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                # Log the user in
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('store')
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    
    return render(request, 'store/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, "You hve been successfully logged out!")
    return redirect('store')
