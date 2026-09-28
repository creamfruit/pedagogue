import { isNative } from "./platform.js";

function setting(name, fallback) {
  return String(import.meta.env[name] ?? fallback).trim().toLowerCase();
}

export const features = {
  audio: setting("VITE_AUDIO_FEATURES", "coming-soon") === "on",
  paidOffers: !isNative,
  inAppPurchases: false,
};

export const DONATION_URL = features.paidOffers ? String(import.meta.env.VITE_DONATION_URL || "").trim() : "";

export function paidOffer(render) {
  return features.paidOffers ? render() : null;
}
