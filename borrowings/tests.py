from datetime import timedelta, date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from books.tests import sample_book
from borrowings.models import Borrowing
from borrowings.serializers import BorrowingDetailSerializer, BorrowingListSerializer
from users.tests import sample_user

BORROWINGS_URL = reverse("borrowings:borrowing-list")


def sample_borrowing(**params):
    defaults = {
        "expected_return_date": (date.today() + timedelta(days=1)),
    }
    defaults.update(params)

    if "user" not in params:
        defaults.update(user=sample_user())
    if "book" not in params:
        defaults.update(book=sample_book())

    return Borrowing.objects.create(**defaults)


class UnauthenticatedBorrowingApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_cant_list_borrowings(self):
        sample_borrowing()

        res = self.client.get(BORROWINGS_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cant_retrieve_borrowing(self):
        borrowing = sample_borrowing()

        url = reverse("borrowings:borrowing-detail", args=[borrowing.id])
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedBorrowingApiTests(TestCase):

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

    def test_list_borrowings(self):
        sample_borrowing(user=self.user)

        res = self.client.get(BORROWINGS_URL)
        serializer = BorrowingListSerializer(Borrowing.objects.all(), many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_retrieve_borrowing(self):
        borrowing = sample_borrowing(user=self.user)

        url = reverse("borrowings:borrowing-detail", args=[borrowing.id])
        res = self.client.get(url)
        serializer = BorrowingDetailSerializer(borrowing)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)
