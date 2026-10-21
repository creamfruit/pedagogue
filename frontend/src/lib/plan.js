import { store } from "./store.js";

export function planLimits() {
  return store.plan?.limits || null;
}

export function isPro() {
  return Boolean(store.plan?.limits?.is_pro);
}

export function canUse(feature) {
  const limits = planLimits();
  if (!limits) return true;
  return Boolean(limits[feature]);
}

export function upgradeCopy(feature) {
  return store.plan?.messages?.[feature] || null;
}
