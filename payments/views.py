import stripe.checkout
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    inline_serializer,
)
from rest_framework import viewsets, mixins, status, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.utils import logger
from stripe import InvalidRequestError

from borrowings.telegram_utils import (
    build_payment_details_message,
    send_telegram_message,
)
from payments.models import Payment
from payments.serializers import PaymentListSerializer, PaymentDetailSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List payments",
        description=(
            "Return a list of payments available to the authenticated user. "
            "Regular users can see only their own payments. "
            "Admin users can see all payments. "
            "Payments may represent either a regular borrowing payment "
            "or an overdue fine."
        ),
        responses=PaymentListSerializer(many=True),
    ),
    retrieve=extend_schema(
        summary="Retrieve payment",
        description=(
            "Return detailed information about a specific payment, "
            "including its associated borrowing and Stripe session data. "
            "A payment may represent either a regular borrowing payment "
            "or an overdue fine."
        ),
        responses=PaymentDetailSerializer,
    ),
    success=extend_schema(
        summary="Confirm successful payment",
        description=(
            "Confirm a Stripe Checkout payment using the session_id query parameter. "
            "If Stripe reports the session as paid, the corresponding local Payment "
            "is marked as PAID."
        ),
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Stripe Checkout Session ID returned via success_url.",
                required=True,
            ),
        ],
        request=None,
        responses={
            200: inline_serializer(
                "PaymentSuccessResponseSerializer",
                fields={
                    "detail": serializers.CharField(),
                    "payment_status": serializers.CharField(),
                },
            )
        },
    ),
    cancel=extend_schema(
        summary="Handle canceled payment",
        description=(
            "Return an informational message when the user cancels Stripe Checkout. "
            "The payment session remains available for up to 24 hours after creation."
        ),
        request=None,
        responses={
            200: inline_serializer(
                "PaymentCancelResponseSerializer",
                fields={
                    "detail": serializers.CharField(),
                },
            )
        },
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

    @action(
        methods=["GET"],
        detail=False,
        permission_classes=(AllowAny,),
    )
    def success(self, request, *args, **kwargs):
        session_id = request.query_params.get("session_id")
        if not session_id:
            raise ValidationError({"session_id": "This query parameter is required."})

        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except InvalidRequestError:
            raise ValidationError("Session_id query parameter is invalid.")

        if session.payment_status == "paid":
            payment = get_object_or_404(Payment, session_id=session.id)

            if payment.status != Payment.Status.PAID:
                payment.status = Payment.Status.PAID
                payment.save()

                message = (
                    "<b>New payment was made:</b>\n"
                    + build_payment_details_message(payment)
                )
                try:
                    send_telegram_message(message)
                except Exception:
                    logger.exception("Failed to send payment notification")

                return Response(
                    {
                        "detail": "Payment confirmed successfully.",
                        "payment_status": "PAID",
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "detail": "This payment has already been paid.",
                    "payment_status": "PAID",
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {"detail": "This payment hasn't been paid yet."},
            status=status.HTTP_200_OK,
        )

    @action(
        methods=["GET"],
        detail=False,
        permission_classes=(AllowAny,),
    )
    def cancel(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "You can still pay later, "
                "the payment link will be active for 24 hours after placing the order."
            },
            status=status.HTTP_200_OK,
        )
