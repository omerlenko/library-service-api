from datetime import timedelta
from unittest.mock import patch, Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from requests import RequestException
from rest_framework import status
from rest_framework.test import APIClient

from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingDetailSerializer,
    BorrowingListSerializer,
)
from borrowings.tasks import check_overdue_borrowings
from borrowings.telegram_utils import (
    build_borrowing_details_message,
    send_telegram_message,
)
from payments.models import Payment
from tests.helpers import sample_borrowing, sample_user, sample_payment, sample_book

BORROWINGS_URL = reverse("borrowings:borrowing-list")


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

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_create_borrowing(self, mock_create_session):
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        mock_create_session.assert_called_once()

        borrowing = Borrowing.objects.get(pk=res.data["id"])
        self.assertEqual(borrowing.user, self.user)
        self.assertEqual(borrowing.book, book)

        book.refresh_from_db()
        self.assertEqual(book.inventory, 2)

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_create_borrowing_fails_if_pending_payments(self, mock_create_session):
        old_book = sample_book(title="Old Book")
        old_borrowing = sample_borrowing(user=self.user, book=old_book)
        sample_payment(borrowing=old_borrowing, status=Payment.Status.PENDING)

        new_book = sample_book(title="New Book", inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": new_book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        new_book.refresh_from_db()
        mock_create_session.assert_not_called()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(new_book.inventory, 3)

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_create_borrowing_if_no_pending_payments(self, mock_create_session):
        old_book = sample_book(title="Old Book")
        old_borrowing = sample_borrowing(user=self.user, book=old_book)
        sample_payment(borrowing=old_borrowing, status=Payment.Status.PAID)

        new_book = sample_book(title="New Book", inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": new_book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        new_book.refresh_from_db()
        mock_create_session.assert_called_once()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(new_book.inventory, 2)

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_another_users_pending_payment_does_not_block_borrowing_creation(
        self, mock_create_session
    ):
        other_user = sample_user(email="other_user@user.com")
        other_book = sample_book(title="Old Book")
        other_borrowing = sample_borrowing(user=other_user, book=other_book)
        sample_payment(borrowing=other_borrowing, status=Payment.Status.PENDING)

        my_book = sample_book(title="New Book", inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": my_book.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        my_book.refresh_from_db()
        mock_create_session.assert_called_once()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(my_book.inventory, 2)

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

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_create_borrowing_assigns_authenticated_user(self, mock_create_session):
        other_user = sample_user(email="other@user.com")
        book = sample_book(inventory=3)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
            "user": other_user.id,
        }

        res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        mock_create_session.assert_called_once()

        borrowing = Borrowing.objects.get(pk=res.data["id"])
        self.assertEqual(borrowing.user, self.user)

    @patch("borrowings.serializers.create_payment_checkout_session")
    def test_return_own_borrowing(self, mock_create_session):
        book = sample_book(inventory=1)
        payload = {
            "expected_return_date": timezone.localdate() + timedelta(days=1),
            "book": book.id,
        }

        res_create = self.client.post(BORROWINGS_URL, payload)

        book.refresh_from_db()
        self.assertEqual(book.inventory, 0)
        mock_create_session.assert_called_once()

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

    def test_telegram_notification_message_builder(self):
        borrowing = sample_borrowing(user=self.user)
        message = build_borrowing_details_message(borrowing)

        self.assertIn(borrowing.book.title, message)
        self.assertIn(borrowing.book.author, message)
        self.assertIn(borrowing.user.email, message)
        self.assertIn(str(borrowing.borrow_date), message)
        self.assertIn(str(borrowing.expected_return_date), message)

    @override_settings(
        TELEGRAM_CHAT_ID="123456",
        TELEGRAM_BOT_TOKEN="test-token",
    )
    @patch("borrowings.telegram_utils.requests.post")
    def test_telegram_notification_message_sender(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}
        mock_post.return_value = mock_response

        send_telegram_message("Test")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        self.assertEqual(args[0], "https://api.telegram.org/bottest-token/sendMessage")
        self.assertEqual(kwargs["data"]["chat_id"], "123456")
        self.assertEqual(kwargs["data"]["text"], "Test")
        self.assertEqual(kwargs["data"]["parse_mode"], "HTML")
        self.assertEqual(kwargs["timeout"], 10)

    @override_settings(
        TELEGRAM_CHAT_ID="123456",
        TELEGRAM_BOT_TOKEN="test-token",
    )
    @patch("borrowings.telegram_utils.requests.post")
    def test_send_telegram_message_request_error(self, mock_post):
        mock_post.side_effect = RequestException("Connection failed")

        with self.assertRaises(RuntimeError):
            send_telegram_message("Test")

    @override_settings(TELEGRAM_CHAT_ID=None, TELEGRAM_BOT_TOKEN=None)
    def test_message_sender_raises_error_when_env_variables_missing(self):
        borrowing = sample_borrowing(user=self.user)
        message = build_borrowing_details_message(borrowing)

        with self.assertRaises(RuntimeError):
            send_telegram_message(message)

    @patch("borrowings.serializers.create_payment_checkout_session")
    @patch("borrowings.serializers.send_telegram_message")
    def test_create_borrowing_triggers_telegram_notification(
        self, mock_send, mock_create_session
    ):
        book = sample_book()
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
        }

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()
        mock_create_session.assert_called_once()

        args, kwargs = mock_send.call_args
        sent_message = args[0]

        self.assertIn("New borrowing created", sent_message)
        self.assertIn(book.title, sent_message)
        self.assertIn(self.user.email, sent_message)

    @patch("borrowings.serializers.send_telegram_message")
    def test_failed_create_does_not_send_notification(self, mock_send):
        book = sample_book(inventory=0)
        payload = {
            "expected_return_date": (timezone.localdate() + timedelta(days=1)),
            "book": book.id,
        }

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(BORROWINGS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        mock_send.assert_not_called()


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


class BorrowingCeleryTaskTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="test_user@user.com",
            password="test12345",
            first_name="Test",
            last_name="User",
            is_staff=False,
        )

    @patch("borrowings.tasks.send_telegram_message")
    def test_overdue_borrowings_trigger_notifications(self, mock_send):
        today = timezone.localdate()
        book = sample_book()

        overdue_borrowing_1 = sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )
        overdue_borrowing_2 = sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )

        Borrowing.objects.filter(pk=overdue_borrowing_1.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today - timedelta(days=1),
        )
        Borrowing.objects.filter(pk=overdue_borrowing_2.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today - timedelta(days=1),
        )

        overdue_borrowing_1.refresh_from_db()
        overdue_borrowing_2.refresh_from_db()

        check_overdue_borrowings()
        calls = mock_send.call_args_list

        self.assertEqual(len(calls), 3)
        self.assertIn("Borrowing overdue", calls[0].args[0])
        self.assertIn("Borrowing overdue", calls[1].args[0])
        self.assertIn("Total overdue borrowings", calls[2].args[0])

    @patch("borrowings.tasks.send_telegram_message")
    def test_no_overdue_borrowings_sends_fallback_message(self, mock_send):
        today = timezone.localdate()
        book = sample_book()

        sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )
        sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )

        check_overdue_borrowings()
        args, kwargs = mock_send.call_args

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(args[0], "<b>No borrowings overdue today!</b>")

    @patch("borrowings.tasks.send_telegram_message")
    def test_returned_borrowings_are_not_overdue(self, mock_send):
        today = timezone.localdate()
        book = sample_book()

        overdue_borrowing_1 = sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )

        Borrowing.objects.filter(pk=overdue_borrowing_1.pk).update(
            borrow_date=today - timedelta(days=3),
            expected_return_date=today - timedelta(days=1),
            actual_return_date=today - timedelta(days=1),
        )
        overdue_borrowing_1.refresh_from_db()

        check_overdue_borrowings()

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args

        self.assertEqual(args[0], "<b>No borrowings overdue today!</b>")

    @patch("borrowings.tasks.send_telegram_message")
    def test_future_borrowings_are_not_overdue(self, mock_send):
        today = timezone.localdate()
        book = sample_book()

        sample_borrowing(
            user=self.user,
            book=book,
            expected_return_date=today + timedelta(days=1),
        )

        check_overdue_borrowings()

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args

        self.assertEqual(args[0], "<b>No borrowings overdue today!</b>")
