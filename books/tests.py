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


class BooksApiTests(TestCase):

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

    def test_create_book(self):
        payload = {
            "author": "Test Author",
            "title": "Test Book",
            "cover": Book.Cover.SOFT,
            "inventory": 10,
            "daily_fee": 0.99,
        }

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

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["inventory"], payload["inventory"])

    def test_delete_book(self):
        book = sample_book()

        url = reverse("books:book-detail", args=[book.id])
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
