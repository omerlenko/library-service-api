from celery import shared_task
from django.utils import timezone

from borrowings.models import Borrowing
from borrowings.telegram_utils import (
    send_telegram_message,
    build_borrowing_details_message,
)


@shared_task
def check_overdue_borrowings():
    today = timezone.localdate()
    overdue_borrowings = Borrowing.objects.select_related("book", "user").filter(
        expected_return_date__lte=today, actual_return_date__isnull=True
    )

    if overdue_borrowings:
        total_overdue_borrowings = 0

        for borrowing in overdue_borrowings:
            message = "<b>Borrowing overdue:</b>\n" + build_borrowing_details_message(
                borrowing
            )
            send_telegram_message(message)
            total_overdue_borrowings += 1

        send_telegram_message(
            f"<b>Total overdue borrowings for today ({today}):</b> {total_overdue_borrowings}."
        )
    else:
        send_telegram_message("<b>No borrowings overdue today!</b>")
