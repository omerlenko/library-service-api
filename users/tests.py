from django.contrib.auth import get_user_model

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.helpers import sample_user
from users.serializers import UserSerializer

USERS_URL = reverse("users:create_user")


class UserApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_create_user(self):
        payload = {
            "email": "test_user@user.com",
            "password": "test12345",
            "first_name": "Test",
            "last_name": "User",
            "is_staff": False,
        }

        res = self.client.post(USERS_URL, payload)
        user = get_user_model().objects.get(email=payload["email"])

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(user.check_password(payload["password"]))
        self.assertNotIn("password", res.data)

    def test_create_user_with_duplicate_email_fails(self):
        sample_user(email="test_user@user.com")
        payload = {
            "email": "test_user@user.com",
            "password": "test12345",
            "first_name": "Test",
            "last_name": "User",
        }

        res = self.client.post(USERS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_token(self):
        sample_user()
        payload = {
            "email": "test_user@user.com",
            "password": "test12345",
        }

        url = reverse("users:token_obtain_pair")
        res = self.client.post(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_manage_user_unauthorized(self):
        url = reverse("users:manage_user")
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authorization_with_correct_token(self):
        sample_user()
        payload = {
            "email": "test_user@user.com",
            "password": "test12345",
        }

        token_url = reverse("users:token_obtain_pair")
        token_res = self.client.post(token_url, payload, format="json")

        self.assertEqual(token_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", token_res.data)

        access_token = token_res.data["access"]
        res = self.client.get(
            reverse("users:manage_user"), HTTP_AUTHORIZE=f"Bearer {access_token}"
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)


class AuthenticatedUserApiTests(TestCase):

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

    def test_retrieve_own_user_info(self):
        url = reverse("users:manage_user")
        res = self.client.get(url)
        serializer = UserSerializer(get_user_model().objects.get(pk=self.user.id))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_update_user(self):
        payload = {
            "first_name": "New",
            "last_name": "Name",
        }

        url = reverse("users:manage_user")
        res = self.client.patch(url, payload)

        self.user.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.first_name, payload["first_name"])
        self.assertEqual(self.user.last_name, payload["last_name"])
