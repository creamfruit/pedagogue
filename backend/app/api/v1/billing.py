import asyncio
import time
from typing import Annotated, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.config import settings
from app.core.rate_limit import enforce
from app.schemas.billing import CheckoutIn, PlanOut, PriceOut, PricesOut, SubscribersOut, UrlOut
from app.services.billing import BillingService, CheckoutRefused, PlanService
from app.services.stripe_gateway import BadWebhook, BillingUnavailable, StripeGateway, get_gateway, verify_webhook

router = APIRouter(prefix="/billing", tags=["billing"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

GatewayDep = Annotated[StripeGateway, Depends(get_gateway)]

PRICE_CACHE_SECONDS = 3600
_price_cache: dict[str, tuple[float, dict]] = {}


def unavailable(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


def trouble() -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Billing is having trouble right now. Try again in a minute.")


@router.get("/plan", response_model=PlanOut)
async def current_plan(user: CurrentUser, session: SessionDep) -> PlanOut:
    return PlanOut(**await PlanService(session).entitlements(user.id))


@router.get("/prices", response_model=PricesOut)
async def prices(gateway: GatewayDep) -> PricesOut:
    found = []
    for interval, price_id in settings.stripe_prices.items():
        summary = {}
        cached = _price_cache.get(price_id)
        if cached and cached[0] > time.monotonic():
            summary = cached[1]
        elif settings.stripe_secret_key.strip():
            try:
                summary = await asyncio.to_thread(gateway.price_summary, price_id)
                _price_cache[price_id] = (time.monotonic() + PRICE_CACHE_SECONDS, summary)
            except Exception:
                summary = {}
        found.append(PriceOut(interval=interval, amount=summary.get("amount"), currency=summary.get("currency")))
    return PricesOut(available=settings.stripe_checkout_ready, trial_days=settings.stripe_trial_days, prices=found)


@router.post("/checkout", response_model=UrlOut)
async def checkout(payload: CheckoutIn, user: CurrentUser, session: SessionDep, gateway: GatewayDep) -> UrlOut:
    if not settings.stripe_checkout_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Pro isn't open for sign-up yet.")
    await enforce("billing", str(user.id))
    try:
        url = await BillingService(session, gateway).checkout_url(user, payload.interval)
    except CheckoutRefused as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except BillingUnavailable as error:
        raise unavailable(error)
    except stripe.StripeError:
        raise trouble()
    return UrlOut(url=url)


@router.post("/portal", response_model=UrlOut)
async def portal(user: CurrentUser, session: SessionDep, gateway: GatewayDep) -> UrlOut:
    await enforce("billing", str(user.id))
    try:
        url = await BillingService(session, gateway).portal_url(user)
    except CheckoutRefused as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except BillingUnavailable as error:
        raise unavailable(error)
    except stripe.StripeError:
        raise trouble()
    return UrlOut(url=url)


@router.post("/webhook")
async def webhook(request: Request, session: SessionDep, gateway: GatewayDep) -> dict:
    payload = await request.body()
    try:
        event = verify_webhook(payload, request.headers.get("stripe-signature"))
    except BillingUnavailable as error:
        raise unavailable(error)
    except BadWebhook:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="that webhook could not be verified")
    try:
        outcome = await BillingService(session, gateway).handle_event(event)
    except BillingUnavailable as error:
        raise unavailable(error)
    except stripe.StripeError:
        raise trouble()
    return {"received": True, "outcome": outcome}


@admin_router.get("/subscribers", response_model=SubscribersOut)
async def subscribers(
    admin: AdminUser,
    session: SessionDep,
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SubscribersOut:
    return SubscribersOut(**await BillingService(session).subscribers(limit=limit, offset=offset, status=status_filter))
