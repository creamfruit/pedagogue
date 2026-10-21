from __future__ import annotations

import json
from typing import Optional

import stripe

from app.core.config import settings

TOLERANCE_SECONDS = 300


class BillingUnavailable(Exception):
    pass


class BadWebhook(Exception):
    pass


class StripeGateway:
    def __init__(self, secret_key: Optional[str] = None) -> None:
        self.secret_key = (secret_key if secret_key is not None else settings.stripe_secret_key).strip()

    def _key(self) -> str:
        if not self.secret_key:
            raise BillingUnavailable("Billing isn't switched on yet.")
        return self.secret_key

    def create_customer(self, email: str, user_id: str) -> str:
        customer = stripe.Customer.create(api_key=self._key(), email=email, metadata={"user_id": user_id})
        return customer["id"]

    def create_checkout(self, *, customer: str, price: str, user_id: str, trial_days: int, success_url: str, cancel_url: str) -> str:
        subscription_data: dict = {"metadata": {"user_id": user_id}}
        if trial_days > 0:
            subscription_data["trial_period_days"] = trial_days
            subscription_data["trial_settings"] = {"end_behavior": {"missing_payment_method": "cancel"}}
        session = stripe.checkout.Session.create(
            api_key=self._key(),
            mode="subscription",
            customer=customer,
            client_reference_id=user_id,
            line_items=[{"price": price, "quantity": 1}],
            subscription_data=subscription_data,
            allow_promotion_codes=True,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session["url"]

    def create_portal(self, *, customer: str, return_url: str) -> str:
        session = stripe.billing_portal.Session.create(api_key=self._key(), customer=customer, return_url=return_url)
        return session["url"]

    def retrieve_subscription(self, subscription_id: str) -> dict:
        return json.loads(str(stripe.Subscription.retrieve(subscription_id, api_key=self._key())))

    def cancel_subscription(self, subscription_id: str) -> None:
        try:
            stripe.Subscription.cancel(subscription_id, api_key=self._key())
        except stripe.InvalidRequestError:
            return

    def price_summary(self, price_id: str) -> dict:
        price = stripe.Price.retrieve(price_id, api_key=self._key())
        recurring = price.get("recurring") or {}
        return {"amount": price.get("unit_amount"), "currency": price.get("currency"), "interval": recurring.get("interval")}


def get_gateway() -> StripeGateway:
    return StripeGateway()


def verify_webhook(payload: bytes, signature: Optional[str], secret: Optional[str] = None) -> dict:
    secret = (secret if secret is not None else settings.stripe_webhook_secret).strip()
    if not secret:
        raise BillingUnavailable("Billing webhooks aren't switched on.")
    try:
        stripe.WebhookSignature.verify_header(payload, signature, secret, tolerance=TOLERANCE_SECONDS)
        event = json.loads(payload)
    except (stripe.SignatureVerificationError, ValueError) as error:
        raise BadWebhook(str(error)) from error
    if not isinstance(event, dict) or "id" not in event or "type" not in event:
        raise BadWebhook("that is not a Stripe event")
    return event
