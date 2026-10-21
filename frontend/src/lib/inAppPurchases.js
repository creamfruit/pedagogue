const REQUIRED_METHODS = ["isAvailable", "loadOfferings", "purchase", "restore", "manage"];

const noProvider = Object.freeze({
  name: "none",
  isAvailable: () => false,
  loadOfferings: async () => [],
  purchase: async () => {
    throw new Error("In-app purchases are not available yet");
  },
  restore: async () => ({ restored: false }),
  manage: async () => {
    throw new Error("In-app purchases are not available yet");
  },
});

let active = noProvider;

export function registerInAppPurchaseProvider(provider) {
  const missing = [!provider?.name && "name", ...REQUIRED_METHODS.filter((method) => typeof provider?.[method] !== "function")].filter(Boolean);
  if (missing.length) throw new Error(`An in-app purchase provider needs: ${missing.join(", ")}`);
  active = provider;
}

export function clearInAppPurchaseProvider() {
  active = noProvider;
}

export const inAppPurchases = {
  get providerName() {
    return active.name;
  },
  get available() {
    return Boolean(active.isAvailable());
  },
  loadOfferings: () => active.loadOfferings(),
  purchase: (offering) => active.purchase(offering),
  restore: () => active.restore(),
  manage: () => active.manage(),
};
