from django.db import models
from django.db.models import Q

from borrowings.models import Borrowing


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        EXPIRED = "EXPIRED", "Expired"

    class Type(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        FINE = "FINE", "Fine"

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    payment_type = models.CharField(
        max_length=10, choices=Type.choices, default=Type.PAYMENT
    )
    borrowing = models.ForeignKey(
        Borrowing, on_delete=models.PROTECT, related_name="payments"
    )
    session_url = models.URLField(max_length=1000)
    session_id = models.CharField(max_length=255, unique=True)
    money_to_pay = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(money_to_pay__gt=0), name="money_to_pay_gt_0"
            )
        ]

    def __str__(self):
        return (
            f"{self.payment_type} for borrowing #{self.borrowing.id} "
            f"for ${self.money_to_pay}. Status: {self.status}"
        )
