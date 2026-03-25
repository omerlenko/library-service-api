from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from payments.models import Payment
from payments.serializers import PaymentListSerializer, PaymentDetailSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List payments",
        description=(
            "Return a list of payments available to the authenticated user. "
            "Regular users can see only their own payments. "
            "Admin users can see all payments."
        ),
        responses=PaymentListSerializer(many=True),
    ),
    retrieve=extend_schema(
        summary="Retrieve payment",
        description="Return detailed information about a specific payment.",
        responses=PaymentDetailSerializer,
    ),
)
class PaymentViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    queryset = Payment.objects.select_related(
        "borrowing", "borrowing__user", "borrowing__book"
    )
    serializer_class = PaymentListSerializer
    permission_classes = (IsAuthenticated,)

    def get_serializer_class(self):
        if self.action == "list":
            return PaymentListSerializer
        if self.action == "retrieve":
            return PaymentDetailSerializer
        return PaymentListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(borrowing__user=self.request.user)

        return queryset
