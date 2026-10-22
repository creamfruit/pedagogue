import { isNative } from "./platform.js";

const STAR_DELAY_MS = 160;

let plugin = null;

function haptics() {
  if (!plugin) plugin = import("@capacitor/haptics");
  return plugin;
}

export function lightTap() {
  if (!isNative) return;
  haptics()
    .then(({ Haptics, ImpactStyle }) => Haptics.impact({ style: ImpactStyle.Light }))
    .catch(() => null);
}

export function stepComplete() {
  if (!isNative) return;
  haptics()
    .then(({ Haptics, ImpactStyle }) => Haptics.impact({ style: ImpactStyle.Medium }))
    .catch(() => null);
}

export function starLit() {
  if (!isNative) return;
  setTimeout(() => {
    haptics()
      .then(({ Haptics, NotificationType }) => Haptics.notification({ type: NotificationType.Success }))
      .catch(() => null);
  }, STAR_DELAY_MS);
}
