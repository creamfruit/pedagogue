import { Capacitor } from "@capacitor/core";

const platform = Capacitor.getPlatform();

export const isNative = Capacitor.isNativePlatform();
export const isIOS = isNative && platform === "ios";
export const isAndroid = isNative && platform === "android";
export const platformName = platform;
