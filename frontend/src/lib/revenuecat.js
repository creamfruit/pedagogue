import { registerInAppPurchaseProvider } from "./inAppPurchases.js";
import { isAndroid, isIOS, isNative, platformName } from "./platform.js";

const UNIT_DAYS = { DAY: 1, WEEK: 7, MONTH: 30, YEAR: 365 };
const PACKAGE_INTERVAL = { MONTHLY: "month", ANNUAL: "year", $rc_monthly: "month", $rc_annual: "year" };
const INTERVAL_ORDER = { month: 0, year: 1 };
const ELIGIBLE = 2;
const CANCELLED_CODE = "1";
const MANAGE_URLS = {
  ios: "https://apps.apple.com/account/subscriptions",
  android: "https://play.google.com/store/account/subscriptions",
};

export const opener = {
  open: (url) => window.open(url, "_blank"),
};

export function revenueCatKey() {
  const env = import.meta.env;
  const raw = isIOS ? env.VITE_REVENUECAT_IOS_API_KEY : isAndroid ? env.VITE_REVENUECAT_ANDROID_API_KEY : "";
  return String(raw || "").trim();
}

function periodDays(unit, count) {
  return (UNIT_DAYS[String(unit || "").toUpperCase()] || 0) * (Number(count) || 0);
}

export function trialDaysOf(product, eligibility) {
  const free = product?.defaultOption?.freePhase;
  if (free?.billingPeriod) return periodDays(free.billingPeriod.unit, free.billingPeriod.value);
  const intro = product?.introPrice;
  if (intro && intro.price === 0 && eligibility?.status === ELIGIBLE) {
    return periodDays(intro.periodUnit, (intro.periodNumberOfUnits || 0) * (intro.cycles || 1));
  }
  return 0;
}

export function intervalOf(aPackage) {
  return PACKAGE_INTERVAL[aPackage?.packageType] || PACKAGE_INTERVAL[aPackage?.identifier] || null;
}

export function describePackage(aPackage, eligibility) {
  const product = aPackage.product;
  return {
    id: aPackage.identifier,
    interval: intervalOf(aPackage),
    price: product.priceString,
    amount: Math.round((Number(product.price) || 0) * 100),
    currency: String(product.currencyCode || "").toLowerCase(),
    trialDays: trialDaysOf(product, eligibility),
  };
}

function wasCancelled(error) {
  return error?.userCancelled === true || String(error?.code) === CANCELLED_CODE;
}

function hasEntitlement(customerInfo) {
  return Object.keys(customerInfo?.entitlements?.active || {}).length > 0;
}

function friendly(error) {
  const text = error?.message || error?.underlyingErrorMessage;
  return new Error(text || "The store couldn't complete that. Nothing was charged.");
}

export function createRevenueCatProvider(purchases, { getUserId }) {
  const packages = new Map();
  let linkedTo;
  let ready = false;

  async function syncUser() {
    const wanted = getUserId() || null;
    if (wanted === linkedTo) return;
    if (wanted) await purchases.logIn({ appUserID: wanted });
    else if (linkedTo) await purchases.logOut();
    linkedTo = wanted;
  }

  async function eligibilityFor(found) {
    if (!isIOS) return {};
    try {
      return await purchases.checkTrialOrIntroductoryPriceEligibility({ productIdentifiers: found.map((item) => item.product.identifier) });
    } catch {
      return {};
    }
  }

  return {
    name: "revenuecat",
    isAvailable: () => ready,
    markReady() {
      ready = true;
    },
    syncUser,
    async loadOfferings() {
      await syncUser();
      const { current } = await purchases.getOfferings();
      const found = (current?.availablePackages || []).filter((item) => intervalOf(item));
      const eligibility = await eligibilityFor(found);
      packages.clear();
      const options = found.map((item) => {
        packages.set(item.identifier, item);
        return describePackage(item, eligibility[item.product.identifier]);
      });
      return options.sort((a, b) => INTERVAL_ORDER[a.interval] - INTERVAL_ORDER[b.interval]);
    },
    async purchase(option) {
      await syncUser();
      const target = packages.get(option?.id);
      if (!target) throw new Error("That plan isn't available right now. Reopen this screen and try again.");
      try {
        const { customerInfo } = await purchases.purchasePackage({ aPackage: target });
        return { entitled: hasEntitlement(customerInfo), cancelled: false };
      } catch (error) {
        if (wasCancelled(error)) return { entitled: false, cancelled: true };
        throw friendly(error);
      }
    },
    async restore() {
      await syncUser();
      try {
        const { customerInfo } = await purchases.restorePurchases();
        return { restored: hasEntitlement(customerInfo) };
      } catch (error) {
        throw friendly(error);
      }
    },
    async manage() {
      let url = "";
      try {
        const { customerInfo } = await purchases.getCustomerInfo();
        url = customerInfo?.managementURL || "";
      } catch {
        url = "";
      }
      opener.open(url || MANAGE_URLS[platformName]);
    },
  };
}

let provider = null;

export async function startPurchases({ getUserId }) {
  if (!isNative || provider) return provider;
  const apiKey = revenueCatKey();
  if (!apiKey) return null;
  try {
    const { Purchases } = await import("@revenuecat/purchases-capacitor");
    await Purchases.configure({ apiKey });
    const created = createRevenueCatProvider(Purchases, { getUserId });
    created.markReady();
    registerInAppPurchaseProvider(created);
    provider = created;
    await created.syncUser().catch(() => {});
  } catch {
    provider = null;
  }
  return provider;
}

export function linkPurchasesUser() {
  return provider ? provider.syncUser().catch(() => {}) : Promise.resolve();
}
