from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, Mock
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from requests import RequestException
from rest_framework import status
from rest_framework.test import APIClient
from stripe import InvalidRequestError
from books.tests import sample_book
from borrowings.models import Borrowing
from borrowings.tests import sample_borrowing
from payments.models import Payment
from payments.serializers import PaymentListSerializer, PaymentDetailSerializer
from payments.utils import calculate_overdue_fine_amount
from users.tests import sample_user

PAYMENTS_URL = reverse("payments:payment-list")


def sample_payment(**params):
    defaults = {
        "status": Payment.Status.PENDING,
        "payment_type": Payment.Type.PAYMENT,
        "session_url": "https://example.com/session/1",
        "session_id": "1",
        "money_to_pay": 10,
    }
    defaults.update(params)

    if "borrowing" not in params:
        defaults.update(borrowing=sample_borrowing())

    return Payment.objects.create(**defaults)


class UnauthenticatedPaymentsApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_cant_list_payments(self):
        sample_payment()

        res = self.client.get(PAYMENTS_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cant_retrieve_payment(self):
        payment = sample_payment()

        url = reverse("payments:payment-detail", args=[payment.id])
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_success_endpoint_fails_with_missing_session_id(self):
        url = reverse("payments:payment-success")
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("payments.views.stripe.checkout.Session.retrieve")
    def test_success_endpoint_fails_with_invalid_session_id(self, mock_retrieve):
        mock_retrieve.side_effect = InvalidRequestError(
            message="Invalid session id",
            param="session_id",
        )

        url = reverse("payments:payment-success")
        res = self.client.get(url, data={"session_id": "invalid_id"})

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("payments.views.send_telegram_message")
    @patch("payments.views.stripe.checkout.Session.retrieve")
    def test_success_endpoint_marks_payment_with_paid_stripe_session_as_paid(
        self, mock_session_retrieve, mock_send_message
    ):
        mock_session = Mock()
        mock_session.payment_status = "paid"
        mock_session.id = "cs_test_123"
        mock_session_retrieve.return_value = mock_session

        payment = sample_payment(
            status=Payment.Status.PENDING, session_id="cs_test_123"
        )
        url = reverse("payments:payment-success")
        res = self.client.get(url, data={"session_id": "cs_test_123"})

        payment.refresh_from_db()
        mock_session_retrieve.assert_called_once()
        mock_send_message.assert_called_once()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("Payment confirmed successfully.", res.data["detail"])
        self.assertEqual(payment.status, Payment.Status.PAID)

    @patch("payments.views.stripe.checkout.Session.retrieve")
    def test_success_endpoint_keeps_payment_with_unpaid_stripe_session_pending(
        self, mock_session_retrieve
    ):
        mock_session = Mock()
        mock_session.payment_status = "unpaid"
        mock_session.id = "cs_test_123"
        mock_session_retrieve.return_value = mock_session

        payment = sample_payment(
            status=Payment.Status.PENDING, session_id="cs_test_123"
        )
        url = reverse("payments:payment-success")
        res = self.client.get(url, data={"session_id": "cs_test_123"})

        payment.refresh_from_db()
        mock_session_retrieve.assert_called_once()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIn("This payment hasn't been paid yet.", res.data["detail"])

    @patch("payments.views.stripe.checkout.Session.retrieve")
    def test_success_endpoint_missing_payment_fails(self, mock_session_retrieve):
        mock_session = Mock()
        mock_session.payment_status = "paid"
        mock_session.id = "cs_test_missing"
        mock_session_retrieve.return_value = mock_session

        url = reverse("payments:payment-success")
        res = self.client.get(url, data={"session_id": "cs_test_missing"})

        mock_session_retrieve.assert_called_once()

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_endpoint_returns_expected_message(self):
        url = reverse("payments:payment-cancel")
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("You can still pay later", res.data["detail"])


class AuthenticatedPaymentsApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="test_user@user.com",
            password="test12345",
            first_name="Test",
            last_name="User",
            is_staff=False,
        )
        self.client.force_authenticate(self.user)

    def test_list_payments(self):
        borrowing = sample_borrowing(user=self.user)
        sample_payment(borrowing=borrowing)

        res = self.client.get(PAYMENTS_URL)
        serializer = PaymentListSerializer(
            Payment.objects.filter(borrowing__user=self.user), many=True
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_user_can_only_see_own_payments(self):
        other_user = sample_user(email="other_user@user.com")
        other_user_borrowing = sample_borrowing(user=other_user)
        other_user_payment = sample_payment(
            borrowing=other_user_borrowing, session_id="1"
        )

        own_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=self.user
        )
        own_payment = sample_payment(borrowing=own_borrowing, session_id="2")

        res = self.client.get(PAYMENTS_URL)

        returned_ids = [payment["id"] for payment in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(own_payment.id, returned_ids)
        self.assertNotIn(other_user_payment.id, returned_ids)

    def test_retrieve_payment(self):
        borrowing = sample_borrowing(user=self.user)
        payment = sample_payment(borrowing=borrowing)

        url = reverse("payments:payment-detail", args=[payment.id])
        res = self.client.get(url)
        serializer = PaymentDetailSerializer(payment)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_user_cannot_retrieve_other_users_payment(self):
        other_user = sample_user(email="other_user@user.com")
        other_user_borrowing = sample_borrowing(user=other_user)
        other_user_payment = sample_payment(
            borrowing=other_user_borrowing,
        )

        url = reverse("payments:payment-detail", args=[other_user_payment.id])
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    @patch("payments.utils.stripe.checkout.Session.create")
    def test_borrowing_creation_creates_payment(self, mock_create_session):
        mock_session = Mock()
        mock_session.url = "https://checkout.stripe.com/test-session"
        mock_session.id = "cs_test_123"
        mock_create_session.return_value = mock_session

        book = sample_book(daily_fee=1)
        payload = {
            "expected_return_date": timezone.localdate() + timedelta(days=1),
            "book": book.id,
        }

        res = self.client.post(reverse("borrowings:borrowing-list"), payload)

        mock_create_session.assert_called_once()

        borrowing = Borrowing.objects.get(pk=res.data["id"])
        payment = Payment.objects.get(borrowing=borrowing)

        self.assertIn(payment, borrowing.payments.all())
        self.assertEqual(
            payment.session_url, "https://checkout.stripe.com/test-session"
        )
        self.assertEqual(payment.session_id, "cs_test_123")
        self.assertEqual(payment.money_to_pay, Decimal("1.00"))

    @patch("payments.utils.stripe.checkout.Session.create")
    def test_if_stripe_fails_borrowing_creation_fails(self, mock_create_session):
        mock_create_session.side_effect = RequestException("Connection failed")

        book = sample_book(inventory=3, daily_fee=1)
        payload = {
            "expected_return_date": timezone.localdate() + timedelta(days=1),
            "book": book.id,
        }

        with self.assertRaises(RequestException):
            self.client.post(reverse("borrowings:borrowing-list"), payload)

        mock_create_session.assert_called_once()
        book.refresh_from_db()

        self.assertEqual(book.inventory, 3)
        self.assertFalse(Borrowing.objects.all().exists())
        self.assertFalse(Payment.objects.all().exists())

    @patch("payments.utils.stripe.checkout.Session.create")
    def test_stripe_is_called_with_correct_arguments(self, mock_create_session):
        mock_session = Mock()
        mock_session.url = "https://checkout.stripe.com/test-session"
        mock_session.id = "cs_test_123"
        mock_create_session.return_value = mock_session

        book = sample_book(daily_fee=1)
        payload = {
            "expected_return_date": timezone.localdate() + timedelta(days=1),
            "book": book.id,
        }

        self.client.post(reverse("borrowings:borrowing-list"), payload)

        args, kwargs = mock_create_session.call_args
        line_item = kwargs["line_items"][0]

        self.assertEqual(kwargs["mode"], "payment")
        self.assertEqual(line_item["quantity"], 1)
        self.assertEqual(line_item["price_data"]["unit_amount"], 100)

    def test_borrowing_returned_on_time_doesnt_create_fine(self):
        today = timezone.localdate()
        book = sample_book(inventory=1)
        borrowing = sample_borrowing(
            user=self.user, expected_return_date=today + timedelta(days=1), book=book
        )

        Borrowing.objects.filter(pk=borrowing.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today,
        )

        borrowing.refresh_from_db()

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(
            Payment.objects.filter(
                borrowing=borrowing, payment_type=Payment.Type.FINE
            ).exists()
        )

    @patch("payments.utils.stripe.checkout.Session.create")
    def test_borrowing_returned_late_creates_one_fine(self, mock_create_session):
        mock_session = Mock()
        mock_session.url = "https://checkout.stripe.com/test-session"
        mock_session.id = "cs_test_123"
        mock_create_session.return_value = mock_session

        today = timezone.localdate()
        book = sample_book(inventory=1)
        borrowing = sample_borrowing(
            user=self.user, expected_return_date=today + timedelta(days=1), book=book
        )

        Borrowing.objects.filter(pk=borrowing.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today - timedelta(days=1),
        )

        borrowing.refresh_from_db()

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)

        mock_create_session.assert_called_once()
        payment = Payment.objects.get(borrowing=borrowing)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(payment.payment_type, Payment.Type.FINE)
        self.assertEqual(payment.session_id, "cs_test_123")
        self.assertEqual(
            payment.session_url, "https://checkout.stripe.com/test-session"
        )

    def test_fine_amount_is_calculated_correctly(self):
        today = timezone.localdate()
        book = sample_book(daily_fee=Decimal("1.00"))
        borrowing = sample_borrowing(
            user=self.user, expected_return_date=today + timedelta(days=1), book=book
        )

        Borrowing.objects.filter(pk=borrowing.pk).update(
            borrow_date=today - timedelta(days=10),
            expected_return_date=today - timedelta(days=5),
            actual_return_date=today,
        )

        borrowing.refresh_from_db()
        amount = calculate_overdue_fine_amount(borrowing, settings.FINE_MULTIPLIER)

        self.assertEqual(amount, Decimal("10.00"))

    @patch("payments.utils.stripe.checkout.Session.create")
    def test_if_stripe_fails_borrowing_return_fails(self, mock_create_session):
        mock_create_session.side_effect = RequestException("Connection failed")

        today = timezone.localdate()
        book = sample_book(inventory=1)
        borrowing = sample_borrowing(
            user=self.user, expected_return_date=today + timedelta(days=1), book=book
        )

        Borrowing.objects.filter(pk=borrowing.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today - timedelta(days=1),
        )

        borrowing.refresh_from_db()

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])

        with self.assertRaises(RequestException):
            self.client.post(url)

        mock_create_session.assert_called_once()
        book.refresh_from_db()
        borrowing.refresh_from_db()

        self.assertEqual(book.inventory, 1)
        self.assertIsNone(borrowing.actual_return_date)
        self.assertFalse(Payment.objects.exists())


class StaffPaymentsApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="admin@admin.com",
            password="test12345",
            first_name="Admin",
            last_name="User",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def test_admin_can_list_all_payments(self):
        user_1 = sample_user(email="user_1@user.com")
        user_1_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=user_1
        )
        user_1_payment = sample_payment(borrowing=user_1_borrowing, session_id="1")

        user_2 = sample_user(email="user_2@user.com")
        user_2_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=user_2
        )
        user_2_payment = sample_payment(borrowing=user_2_borrowing, session_id="2")

        res = self.client.get(PAYMENTS_URL)

        returned_ids = [payment["id"] for payment in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(user_1_payment.id, returned_ids)
        self.assertIn(user_2_payment.id, returned_ids)

    def test_admin_can_retrieve_any_payment(self):
        other_user = sample_user(email="other_user@user.com")
        other_user_borrowing = sample_borrowing(user=other_user)
        other_user_payment = sample_payment(
            borrowing=other_user_borrowing,
        )

        url = reverse("payments:payment-detail", args=[other_user_payment.id])
        res = self.client.get(url)
        serializer = PaymentDetailSerializer(other_user_payment)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)
