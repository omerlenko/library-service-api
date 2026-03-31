import requests
from borrowings.models import Borrowing
from django.conf import settings
from payments.models import Payment


def build_borrowing_details_message(borrowing: Borrowing) -> str:
    text = (
        f"Borrowing id: {borrowing.id}\n"
        f"Book: {borrowing.book.title} by {borrowing.book.author}\n"
        f"User: {borrowing.user.email}\n"
        f"Borrow date: {borrowing.borrow_date}\n"
        f"Expected return: {borrowing.expected_return_date}"
    )
    return text


def build_payment_details_message(payment: Payment) -> str:
    borrowing = payment.borrowing

    text = (
        f"Payment id: {payment.id}\n"
        f"Payment type: {payment.payment_type}\n"
        f"Payment amount: ${payment.money_to_pay}\n"
        f"Book: {borrowing.book.title} by {borrowing.book.author}\n"
        f"User: {borrowing.user.email}\n"
    )
    return text


def send_telegram_message(text: str):
    chat_id = settings.TELEGRAM_CHAT_ID
    token = settings.TELEGRAM_BOT_TOKEN

    if not chat_id or not token:
        raise RuntimeError("Telegram environment variables are not configured.")

    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        res = requests.post(url, data=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram request failed: {exc}") from exc

    if not data.get("ok"):
        description = data.get("description", "Unknown Telegram API Error")
        raise RuntimeError(f"Telegram API error: {description}")

    return data
