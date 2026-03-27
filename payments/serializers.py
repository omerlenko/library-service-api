from rest_framework import serializers
from payments.models import Payment


class PaymentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "borrowing",
            "payment_type",
            "money_to_pay",
        )


class PaymentDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "payment_type",
            "borrowing",
            "session_url",
            "session_id",
            "money_to_pay",
        )
