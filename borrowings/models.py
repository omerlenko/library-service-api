from django.db import models
from django.db.models import Q, F

from books.models import Book
from library_service_api.settings import AUTH_USER_MODEL


class Borrowing(models.Model):
    borrow_date = models.DateField(auto_now_add=True)
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="borrowings")
    user = models.ForeignKey(
        AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="borrowings"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(expected_return_date__gt=F("borrow_date")),
                name="expected_return_date_gt_borrow_date",
            ),
            models.CheckConstraint(
                condition=Q(actual_return_date__isnull=True)
                | Q(actual_return_date__gte=F("borrow_date")),
                name="actual_return_date_gte_borrow_date",
            ),
        ]

    def __str__(self):
        return f"{self.book.title} borrowed by {self.user.email} on {self.borrow_date}"
