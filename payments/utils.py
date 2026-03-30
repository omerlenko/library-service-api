from decimal import Decimal
from django.urls import reverse
from borrowings.models import Borrowing
import stripe
from library_service_api import settings
from payments.models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


def calculate_borrowing_payment_amount(borrowing: Borrowing) -> Decimal:
    book = borrowing.book
    borrowing_duration = borrowing.expected_return_date - borrowing.borrow_date
    total_price = book.daily_fee * Decimal(borrowing_duration.days)

    return total_price


def calculate_overdue_fine_amount(borrowing: Borrowing, multiplier: Decimal) -> Decimal:
    book = borrowing.book
    overdue_duration = borrowing.actual_return_date - borrowing.expected_return_date
    total_price = book.daily_fee * Decimal(overdue_duration.days) * multiplier

    return total_price


def create_payment_checkout_session(
    borrowing: Borrowing, amount: Decimal, payment_type: str, request
) -> Payment:
    book = borrowing.book
    unit_amount = int(amount * Decimal("100"))

    prefix = "Overdue fine for " if payment_type == Payment.Type.FINE else ""
    product_name = f"{prefix}{book.title} by {book.author}"

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
                        "name": product_name,
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
        payment_type=payment_type,
        borrowing=borrowing,
        session_url=session.url,
        session_id=session.id,
        money_to_pay=amount,
    )

    return payment
