import { isAndroid, isNative, platformName } from "./platform.js";

export async function setupNative({ onBack } = {}) {
  if (!isNative) return;
  document.documentElement.classList.add("is-native", `is-${platformName}`);
  if (isAndroid && onBack) {
    const { App } = await import("@capacitor/app");
    App.addListener("backButton", () => {
      if (!onBack()) App.minimizeApp();
    });
  }
}
