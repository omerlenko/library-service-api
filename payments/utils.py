from decimal import Decimal
from django.urls import reverse
from borrowings.models import Borrowing
import stripe
from library_service_api import settings
from payments.models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_borrowing_stripe_session(borrowing: Borrowing, request):
    book = borrowing.book
    borrowing_duration = borrowing.expected_return_date - borrowing.borrow_date
    total_price = book.daily_fee * Decimal(borrowing_duration.days)
    unit_amount = int(total_price * Decimal("100"))

    success_url = (
        request.build_absolute_uri(reverse("payments:payment-success"))
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(reverse("payments:payment-cancel"))

    session = stripe.checkout.Session.create(
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"{book.title} by {book.author}",
                    },
                    "unit_amount": unit_amount,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
    )

    payment = Payment.objects.create(
        status=Payment.Status.PENDING,
        payment_type=Payment.Type.PAYMENT,
        borrowing=borrowing,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=total_price,
    )

    return payment
