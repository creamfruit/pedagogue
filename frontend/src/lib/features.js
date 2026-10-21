import { isNative } from "./platform.js";

function setting(name, fallback) {
  return String(import.meta.env[name] ?? fallback).trim().toLowerCase();
}

export const features = {
  audio: ["on", "true"].includes(setting("VITE_AUDIO_FEATURES", "coming-soon")),
  paidOffers: !isNative,
};

export const COMING_SOON = "Coming soon";

function webAddress(value) {
  const found = String(value || "").trim();
  return /^https?:\/\//i.test(found) ? found : "";
}

export const DONATION_URL = features.paidOffers ? webAddress(import.meta.env.VITE_DONATION_URL) : "";
