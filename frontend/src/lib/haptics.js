import { isNative } from "./platform.js";

let plugin = null;

export function lightTap() {
  if (!isNative) return;
  if (!plugin) plugin = import("@capacitor/haptics");
  plugin.then(({ Haptics, ImpactStyle }) => Haptics.impact({ style: ImpactStyle.Light })).catch(() => null);
}
