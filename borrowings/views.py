from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter
from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from borrowings.models import Borrowing
from borrowings.serializers import (
    BorrowingListSerializer,
    BorrowingDetailSerializer,
    BorrowingCreateSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List borrowings",
        description=(
            "Return a list of borrowings available to the authenticated user. "
            "Regular users can see only their own borrowings. "
            "Admin users can see all borrowings and may additionally filter by user_id."
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
        description="Return detailed information about a specific borrowing.",
        responses=BorrowingDetailSerializer,
    ),
    create=extend_schema(
        summary="Create borrowing",
        description=(
            "Create a new borrowing for the authenticated user. "
            "The selected book must be in stock, and expected_return_date "
            "must be at least one day in the future."
        ),
        request=BorrowingCreateSerializer,
        responses=BorrowingCreateSerializer,
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
