import { api } from "../api/client.js";
import { features } from "./features.js";
import { inAppPurchases } from "./inAppPurchases.js";
import { store } from "./store.js";

export const PRICING_PATH = "/pricing";

export const redirect = {
  to: (url) => window.location.assign(url),
};

export function stripeAllowed() {
  return features.paidOffers;
}

export function billingMode() {
  if (stripeAllowed()) return "stripe";
  return inAppPurchases.available ? "in-app" : "none";
}

export function offersVisible() {
  return billingMode() !== "none";
}

const INTERVAL_LABEL = { month: "Monthly", year: "Yearly" };

export function formatPrice(amount, currency) {
  if (amount === null || amount === undefined || !currency) return "";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: currency.toUpperCase() }).format(amount / 100);
  } catch {
    return `${(amount / 100).toFixed(2)} ${currency.toUpperCase()}`;
  }
}

function stripeOption(price, trialDays) {
  return {
    id: price.interval,
    interval: price.interval,
    label: INTERVAL_LABEL[price.interval] || price.interval,
    price: formatPrice(price.amount, price.currency),
    amount: price.amount,
    currency: price.currency,
    trialDays,
  };
}

export async function loadOptions() {
  const mode = billingMode();
  if (mode === "stripe") {
    const shown = await api.billingPrices();
    if (!shown.available) return [];
    return shown.prices.map((price) => stripeOption(price, shown.trial_days));
  }
  if (mode === "in-app") {
    const offerings = await inAppPurchases.loadOfferings();
    return offerings.map((offering) => ({ label: INTERVAL_LABEL[offering.interval] || offering.interval, trialDays: 0, ...offering }));
  }
  return [];
}

export async function subscribe(option) {
  const mode = billingMode();
  if (mode === "stripe") {
    const { url } = await api.billingCheckout({ interval: option.interval });
    redirect.to(url);
    return { redirected: true };
  }
  if (mode === "in-app") {
    const result = await inAppPurchases.purchase(option);
    await store.refreshPlan();
    return { redirected: false, ...result };
  }
  throw new Error("Subscriptions can't be started here");
}

export async function manageBilling() {
  const mode = billingMode();
  if (mode === "stripe") {
    const { url } = await api.billingPortal();
    redirect.to(url);
    return { redirected: true };
  }
  if (mode === "in-app") {
    await inAppPurchases.manage();
    return { redirected: false };
  }
  throw new Error("Billing can't be managed here");
}

export async function restorePurchases() {
  if (billingMode() !== "in-app") return { restored: false };
  const result = await inAppPurchases.restore();
  await store.refreshPlan();
  return result;
}
