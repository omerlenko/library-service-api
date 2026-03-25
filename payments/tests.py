from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from books.tests import sample_book
from borrowings.tests import sample_borrowing
from payments.models import Payment
from payments.serializers import PaymentListSerializer, PaymentDetailSerializer
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
