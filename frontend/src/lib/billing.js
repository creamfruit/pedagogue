import { isNative } from "./platform.js";

export const PRICING_PATH = "/pricing";

export function offersVisible() {
  return !isNative;
}
