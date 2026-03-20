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

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cant_return_borrowing(self):
        borrowing = sample_borrowing()

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)

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
        serializer = BorrowingListSerializer(
            Borrowing.objects.filter(user=self.user), many=True
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_user_can_only_see_own_borrowings(self):
        other_user = sample_user(email="other_user@user.com")

        other_user_borrowing = sample_borrowing(user=other_user)
        own_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=self.user
        )

        res = self.client.get(BORROWINGS_URL)

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(own_borrowing.id, returned_ids)
        self.assertNotIn(other_user_borrowing.id, returned_ids)

    def test_filter_borrowings_by_is_active(self):
        non_returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=self.user
        )
        returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"),
            user=self.user,
            actual_return_date=timezone.localdate(),
        )

        res = self.client.get(BORROWINGS_URL, data={"is_active": "true"})

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(non_returned_borrowing.id, returned_ids)
        self.assertNotIn(returned_borrowing.id, returned_ids)

    def test_filter_borrowings_by_is_active_false(self):
        non_returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=self.user
        )
        returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"),
            user=self.user,
            actual_return_date=timezone.localdate(),
        )

        res = self.client.get(BORROWINGS_URL, data={"is_active": "false"})

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(returned_borrowing.id, returned_ids)
        self.assertNotIn(non_returned_borrowing.id, returned_ids)

    def test_filter_borrowings_by_user_id_doesnt_bypass_ownership(self):
        other_user = sample_user(email="other_user@user.com")

        other_user_borrowing = sample_borrowing(user=other_user)
        own_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=self.user
        )

        res = self.client.get(BORROWINGS_URL, data={"user_id": other_user.id})

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(own_borrowing.id, returned_ids)
        self.assertNotIn(other_user_borrowing.id, returned_ids)

    def test_retrieve_borrowing(self):
        borrowing = sample_borrowing(user=self.user)

        url = reverse("borrowings:borrowing-detail", args=[borrowing.id])
        res = self.client.get(url)
        serializer = BorrowingDetailSerializer(borrowing)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_user_cannot_retrieve_other_users_borrowing(self):
        other_user = sample_user(email="other_user@user.com")
        borrowing = sample_borrowing(user=other_user)

        url = reverse("borrowings:borrowing-detail", args=[borrowing.id])
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

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

    def test_return_own_borrowing(self):
        book = sample_book(inventory=1)
        payload = {
            "expected_return_date": timezone.localdate() + timedelta(days=1),
            "book": book.id,
        }

        res_create = self.client.post(BORROWINGS_URL, payload)

        book.refresh_from_db()
        self.assertEqual(book.inventory, 0)

        url = reverse(
            "borrowings:borrowing-return-borrowing", args=[res_create.data["id"]]
        )
        res_return = self.client.post(url)
        borrowing = Borrowing.objects.get(pk=res_create.data["id"])

        borrowing.refresh_from_db()
        book.refresh_from_db()

        self.assertEqual(res_return.status_code, status.HTTP_200_OK)
        self.assertEqual(borrowing.actual_return_date, timezone.localdate())
        self.assertEqual(book.inventory, 1)

    def test_cant_return_own_borrowing_twice(self):
        borrowing = sample_borrowing(
            user=self.user, actual_return_date=timezone.localdate()
        )
        book = borrowing.book
        old_inventory = book.inventory

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)

        book.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(book.inventory, old_inventory)

    def test_user_cant_return_other_users_borrowing(self):
        other_user = sample_user(email="other_user@user.com")
        borrowing = sample_borrowing(user=other_user)

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class StaffBorrowingApiTests(TestCase):

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

    def test_admin_can_see_all_borrowings(self):
        user_1 = sample_user(email="user_1@user.com")
        user_2 = sample_user(email="user_2@user.com")

        user_1_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=user_1
        )
        user_2_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=user_2
        )

        res = self.client.get(BORROWINGS_URL)

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(user_1_borrowing.id, returned_ids)
        self.assertIn(user_2_borrowing.id, returned_ids)

    def test_filter_borrowings_by_is_active(self):
        other_user = sample_user(email="other@user.com")

        non_returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=other_user
        )
        returned_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"),
            user=other_user,
            actual_return_date=timezone.localdate(),
        )

        res = self.client.get(BORROWINGS_URL, data={"is_active": "true"})

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(non_returned_borrowing.id, returned_ids)
        self.assertNotIn(returned_borrowing.id, returned_ids)

    def test_filter_borrowings_by_user_id(self):
        user_1 = sample_user(email="user_1@user.com")
        user_2 = sample_user(email="user_2@user.com")

        user_1_borrowing = sample_borrowing(
            book=sample_book(title="Book 1"), user=user_1
        )
        user_2_borrowing = sample_borrowing(
            book=sample_book(title="Book 2"), user=user_2
        )

        res = self.client.get(BORROWINGS_URL, data={"user_id": user_2.id})

        returned_ids = [borrowing["id"] for borrowing in res.data]

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(user_2_borrowing.id, returned_ids)
        self.assertNotIn(user_1_borrowing.id, returned_ids)

    def test_admin_can_return_other_users_borrowing(self):
        other_user = sample_user(email="other@user.com")
        borrowing = sample_borrowing(user=other_user)

        url = reverse("borrowings:borrowing-return-borrowing", args=[borrowing.id])
        res = self.client.post(url)
        borrowing = Borrowing.objects.get(pk=res.data["id"])

        borrowing.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(borrowing.actual_return_date, timezone.localdate())
