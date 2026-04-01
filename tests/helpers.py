from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from books.models import Book
from borrowings.models import Borrowing
from payments.models import Payment


def sample_book(**params):
    defaults = {
        "author": "Test Author",
        "title": "Test Book",
        "cover": Book.Cover.SOFT,
        "inventory": 10,
        "daily_fee": 0.99,
    }

    defaults.update(params)

    return Book.objects.create(**defaults)


def sample_book_payload(**params):
    payload = {
        "author": "Test Author",
        "title": "Test Book",
        "cover": Book.Cover.SOFT,
        "inventory": 10,
        "daily_fee": "0.99",
    }
    payload.update(params)
    return payload


def sample_borrowing(**params):
    defaults = {
        "expected_return_date": (timezone.localdate() + timedelta(days=1)),
    }
    defaults.update(params)

    if "user" not in params:
        defaults.update(user=sample_user())
    if "book" not in params:
        defaults.update(book=sample_book())

    return Borrowing.objects.create(**defaults)


def sample_payment(**params):
    defaults = {
        "status": Payment.Status.PENDING,
        "payment_type": Payment.Type.PAYMENT,
        "session_url": "https://example.com/session/1",
        "session_id": "1",
        "money_to_pay": Decimal("10"),
    }
    defaults.update(params)

    if "borrowing" not in params:
        defaults.update(borrowing=sample_borrowing())

    return Payment.objects.create(**defaults)


def sample_user(**params):
    defaults = {
        "email": "test_user@user.com",
        "password": "test12345",
        "first_name": "Test",
        "last_name": "User",
        "is_staff": False,
    }

    defaults.update(params)

    return get_user_model().objects.create_user(**defaults)
