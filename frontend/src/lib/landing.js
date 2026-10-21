export const LANDING_PATH = "/welcome";

export function landingTarget({ pathname, authenticated, native }) {
  if (native || authenticated) return null;
  return pathname === "/" ? LANDING_PATH : null;
}
