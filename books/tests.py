from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from books.models import Book
from books.serializers import BookListSerializer, BookSerializer

BOOKS_URL = reverse("books:book-list")


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


class UnauthenticatedBooksApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_list_books(self):
        sample_book()

        res = self.client.get(BOOKS_URL)
        serializer = BookListSerializer(Book.objects.all(), many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_retrieve_book(self):
        book = sample_book()

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.get(url)
        serializer = BookSerializer(book)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_cant_create_book(self):
        payload = sample_book_payload()

        res = self.client.post(BOOKS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cant_update_book(self):
        book = sample_book(inventory=0)

        payload = {
            "inventory": 20,
        }

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cant_delete_book(self):
        book = sample_book()

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedBooksApiTests(TestCase):

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

    def test_cant_create_book(self):
        payload = sample_book_payload()

        res = self.client.post(BOOKS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cant_update_book(self):
        book = sample_book(inventory=0)

        payload = {
            "inventory": 20,
        }

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cant_delete_book(self):
        book = sample_book()

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class StaffBooksApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="admin@user.com",
            password="test12345",
            first_name="Admin",
            last_name="User",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def test_create_book(self):
        payload = sample_book_payload()

        res = self.client.post(BOOKS_URL, payload)
        serializer = BookSerializer(Book.objects.get(pk=res.data["id"]))

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data, serializer.data)

    def test_update_book(self):
        book = sample_book(inventory=0)

        payload = {
            "inventory": 20,
        }

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.patch(url, payload)
        book.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["inventory"], payload["inventory"])
        self.assertEqual(book.inventory, payload["inventory"])

    def test_delete_book(self):
        book = sample_book()

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Book.objects.filter(id=book.id).exists())

    def test_create_book_with_JWT_token_authorization(self):
        client = APIClient()

        payload_token = {
            "email": self.user.email,
            "password": "test12345",
        }

        token_url = reverse("users:token_obtain_pair")
        token_res = client.post(token_url, payload_token, format="json")

        self.assertEqual(token_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", token_res.data)

        access_token = token_res.data["access"]

        payload_book = sample_book_payload()

        res = client.post(
            BOOKS_URL, payload_book, HTTP_AUTHORIZE=f"Bearer {access_token}"
        )
        serializer = BookSerializer(Book.objects.get(pk=res.data["id"]))

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data, serializer.data)
