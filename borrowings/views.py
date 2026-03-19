from drf_spectacular.utils import extend_schema_view, extend_schema
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
        description="Return a list of borrowings available to the authenticated user.",
        responses=BorrowingListSerializer(many=True),
    ),
    retrieve=extend_schema(
        summary="Retrieve borrowing",
        description="Return detailed information about a specific borrowing.",
        responses=BorrowingDetailSerializer,
    ),
    create=extend_schema(
        summary="Create borrowing",
        description="Create a new borrowing.",
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
        elif self.action == "retrieve":
            return BorrowingDetailSerializer
        elif self.action == "create":
            return BorrowingCreateSerializer
        return BorrowingListSerializer
