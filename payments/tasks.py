import stripe.checkout
from celery import shared_task
from django.conf import settings

from payments.models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


@shared_task
def check_expired_payments():
    pending_payments = Payment.objects.filter(status=Payment.Status.PENDING)
    counter = 0

    if pending_payments:

        for payment in pending_payments:
            session = stripe.checkout.Session.retrieve(payment.session_id)

            if session and session.status == "expired":
                payment.status = Payment.Status.EXPIRED
                payment.save()
                counter += 1

    return f"Payments expired: {counter}"
