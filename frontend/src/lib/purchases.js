import { features } from "./features.js";

export const PRODUCTS = Object.freeze([]);

export function purchasesAvailable() {
  return features.inAppPurchases;
}

export async function loadProducts() {
  return [];
}

export async function purchase() {
  throw new Error("In-app purchases are not available yet");
}

export async function restorePurchases() {
  return [];
}
