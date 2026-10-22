import { isNative } from "./platform.js";

const nothing = () => {};

async function nativeKeepAwake() {
  try {
    const { KeepAwake } = await import("@capacitor-community/keep-awake");
    await KeepAwake.keepAwake();
    return () => {
      KeepAwake.allowSleep().catch(() => null);
    };
  } catch {
    return null;
  }
}

async function browserKeepAwake() {
  if (typeof navigator === "undefined" || !("wakeLock" in navigator)) return nothing;
  let sentinel = null;
  let released = false;
  const acquire = async () => {
    try {
      sentinel = await navigator.wakeLock.request("screen");
    } catch {
      sentinel = null;
    }
  };
  const onVisible = () => {
    if (!released && document.visibilityState === "visible") acquire();
  };
  document.addEventListener("visibilitychange", onVisible);
  await acquire();
  return () => {
    released = true;
    document.removeEventListener("visibilitychange", onVisible);
    if (sentinel) sentinel.release().catch(() => null);
    sentinel = null;
  };
}

export async function keepAwake() {
  if (isNative) {
    const release = await nativeKeepAwake();
    if (release) return release;
  }
  return browserKeepAwake();
}
