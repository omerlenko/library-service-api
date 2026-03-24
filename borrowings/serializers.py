from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from books.models import Book
from books.serializers import BookSerializer, BookListSerializer
from borrowings.models import Borrowing
from borrowings.telegram_utils import (
    build_borrowing_details_message,
    send_telegram_message,
)


class BorrowingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = (
            "id",
            "expected_return_date",
            "book",
        )

    def validate_expected_return_date(self, expected_date):
        if expected_date and expected_date <= timezone.localdate():
            raise serializers.ValidationError(
                "Expected return date must be at least one day in the future."
            )

        return expected_date

    def create(self, validated_data):
        request = self.context["request"]
        book = validated_data["book"]

        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=book.pk)

            if book.inventory < 1:
                raise serializers.ValidationError(
                    {"book": "No more copies of the book left in inventory."}
                )

            borrowing = Borrowing.objects.create(user=request.user, **validated_data)

            book.inventory -= 1
            book.save()

            message = (
                "<b>New borrowing created:</b>\n"
                + build_borrowing_details_message(borrowing)
            )
            transaction.on_commit(lambda: send_telegram_message(message), robust=True)

        return borrowing


class BorrowingUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "email", "first_name", "last_name")


class BorrowingListSerializer(serializers.ModelSerializer):
    book = BookListSerializer(read_only=True)
    user = serializers.SlugRelatedField(slug_field="email", read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
        )
        read_only_fields = fields


class BorrowingDetailSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    user = BorrowingUserSerializer(read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
        )
        read_only_fields = fields
