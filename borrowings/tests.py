from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from books.tests import sample_book
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingDetailSerializer,
    BorrowingListSerializer,
)
from users.tests import sample_user

BORROWINGS_URL = reverse("borrowings:borrowing-list")


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

    def test_cant_create_borrowing(self):
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": sample_book().id,
        }

        res = self.client.get(BORROWINGS_URL, payload)

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

    def test_create_borrowing(self):
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        borrowing = Borrowing.objects.get(pk=res.data["id"])
        self.assertEqual(borrowing.user, self.user)
        self.assertEqual(borrowing.book, book)

        book.refresh_from_db()
        self.assertEqual(book.inventory, 2)

    def test_create_borrowing_fails_if_book_out_of_stock(self):
        book = sample_book(inventory=0)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Borrowing.objects.filter(user=self.user, book=book).exists())

    def test_create_borrowing_with_today_return_date_fails(self):
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": timezone.localdate(),
            "book": book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_borrowing_with_past_return_date_fails(self):
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": timezone.localdate() - timedelta(days=1),
            "book": book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_borrowing_assigns_authenticated_user(self):
        other_user = sample_user(email="other@user.com")
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
            "user": other_user.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        borrowing = Borrowing.objects.get(pk=res.data["id"])
        self.assertEqual(borrowing.user, self.user)
