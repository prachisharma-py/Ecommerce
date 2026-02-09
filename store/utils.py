from .models import Cart, CartItem, Products

def merge_session_cart_to_db(request, user):
    session_cart = request.session.get('cart')

    if not session_cart:
        return

    cart, _ = Cart.objects.get_or_create(user=user)

    for product_id, quantity in session_cart.items():
        product = Products.objects.get(id=product_id)
        cart_item, _ = CartItem.objects.get_or_create(cart=cart, product=product)
        cart_item.quantity += quantity
        cart_item.save()

    del request.session['cart']
