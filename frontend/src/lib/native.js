import { isAndroid, isNative, platformName } from "./platform.js";

const NAVY = "#0a1120";

async function styleStatusBar() {
  try {
    const { StatusBar, Style } = await import("@capacitor/status-bar");
    await StatusBar.setStyle({ style: Style.Dark });
    if (isAndroid) await StatusBar.setBackgroundColor({ color: NAVY });
  } catch {
    return;
  }
}

export async function setupNative({ onBack, onResume } = {}) {
  if (!isNative) return;
  document.documentElement.classList.add("is-native", `is-${platformName}`);
  styleStatusBar();
  const { App } = await import("@capacitor/app");
  if (isAndroid && onBack) {
    App.addListener("backButton", () => {
      if (!onBack()) App.minimizeApp();
    });
  }
  if (onResume) {
    App.addListener("appStateChange", ({ isActive }) => {
      if (isActive) onResume();
    });
  }
}

export async function hideSplash() {
  if (!isNative) return;
  try {
    const { SplashScreen } = await import("@capacitor/splash-screen");
    await SplashScreen.hide({ fadeOutDuration: 250 });
  } catch {
    return;
  }
}
