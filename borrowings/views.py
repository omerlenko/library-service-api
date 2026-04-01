from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingListSerializer,
    BorrowingDetailSerializer,
    BorrowingCreateSerializer,
)
from library_service_api.settings import FINE_MULTIPLIER
from payments.models import Payment
from payments.utils import (
    calculate_overdue_fine_amount,
    create_payment_checkout_session,
)


@extend_schema_view(
    list=extend_schema(
        summary="List borrowings",
        description=(
            "Return a list of borrowings available to the authenticated user. "
            "Regular users can see only their own borrowings. "
            "Admin users can see all borrowings "
            "and may additionally filter by user_id. "
            "Each borrowing includes its associated payments."
        ),
        parameters=[
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description=(
                    "Filter borrowings by active status. "
                    "Use true for active borrowings (not returned yet), "
                    "false for returned borrowings."
                ),
                required=False,
            ),
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description=(
                    "Filter borrowings by user id. "
                    "This parameter is intended for admin users only."
                ),
                required=False,
            ),
        ],
        responses=BorrowingListSerializer(many=True),
    ),
    retrieve=extend_schema(
        summary="Retrieve borrowing",
        description=(
            "Return detailed information about a specific borrowing, "
            "including all associated payments such as "
            "regular payments and overdue fines."
        ),
        responses=BorrowingDetailSerializer,
    ),
    create=extend_schema(
        summary="Create borrowing",
        description=(
            "Create a new borrowing for the authenticated user. "
            "The selected book must be in stock, and expected_return_date "
            "must be at least one day in the future. "
            "On successful creation, the system decreases the book inventory, "
            "creates a Stripe Checkout payment session, creates a pending Payment "
            "associated with the borrowing, and returns the detailed borrowing "
            "representation including its payments."
        ),
        request=BorrowingCreateSerializer,
        responses={201: BorrowingDetailSerializer},
    ),
    return_borrowing=extend_schema(
        summary="Return borrowing",
        description=(
            "Mark a borrowing as returned and increase the book inventory by 1. "
            "If the borrowing is overdue, "
            "the system also creates a pending FINE payment "
            "and a Stripe Checkout session for the overdue amount. "
            "The response returns the updated borrowing "
            "including its associated payments."
        ),
        request=None,
        responses={200: BorrowingDetailSerializer},
    ),
)
class BorrowingViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
):
    queryset = Borrowing.objects.select_related("user", "book")
    serializer_class = BorrowingListSerializer
    permission_classes = (IsAuthenticated,)

    def get_serializer_class(self):
        if self.action == "list":
            return BorrowingListSerializer
        if self.action == "retrieve":
            return BorrowingDetailSerializer
        if self.action == "create":
            return BorrowingCreateSerializer
        return BorrowingListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        user_id = self.request.query_params.get("user_id")

        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        else:
            if user_id:
                queryset = queryset.filter(user__id=user_id)

        if is_active:
            if is_active.lower() == "true":
                queryset = queryset.filter(actual_return_date__isnull=True)
            elif is_active.lower() == "false":
                queryset = queryset.filter(actual_return_date__isnull=False)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        borrowing = serializer.save()
        instance = self.get_queryset().get(pk=borrowing.pk)
        out = BorrowingDetailSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(
        methods=["POST"],
        detail=True,
        permission_classes=(IsAuthenticated,),
        url_path="return",
    )
    def return_borrowing(self, request, *args, **kwargs):
        with transaction.atomic():
            borrowing = get_object_or_404(
                self.get_queryset().select_for_update().select_related("book"),
                pk=kwargs["pk"],
            )

            if borrowing.actual_return_date is not None:
                raise ValidationError(
                    {"actual_return_date": "This borrowing has already been returned."}
                )

            borrowing.actual_return_date = timezone.localdate()
            borrowing.save()

            borrowing.book.inventory += 1
            borrowing.book.save()

            if borrowing.actual_return_date > borrowing.expected_return_date:
                amount = calculate_overdue_fine_amount(borrowing, FINE_MULTIPLIER)
                create_payment_checkout_session(
                    borrowing, amount, Payment.Type.FINE, request
                )

        serializer = BorrowingDetailSerializer(borrowing, context={"request": request})
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
