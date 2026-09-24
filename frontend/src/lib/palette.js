export const YELLOW = "#f4c14a";
export const YELLOW_SOFT = "#ffe3a3";
export const ORANGE = "#ef7f3c";
export const ORANGE_SOFT = "#f6a97a";
export const PINK = "#ef4d80";
export const PINK_SOFT = "#f88fae";
export const INK = "#0a0a0c";
export const STAR_DEFAULT = "#cdd3dc";
export const FROZEN = "#cdd3dc";
export const NEUTRAL = "#8a8f99";

export const LINK_TYPE_COLOR = {
  composer: YELLOW,
  technique: ORANGE,
  era_genre: PINK,
};

export const ERA_COLOR = {
  Baroque: YELLOW_SOFT,
  Classical: YELLOW,
  Romantic: ORANGE,
  Impressionist: ORANGE_SOFT,
  Modern: PINK,
  Contemporary: PINK_SOFT,
};

export function difficultyColor(difficulty) {
  if (difficulty >= 90) return "#ffffff";
  if (difficulty >= 75) return YELLOW_SOFT;
  if (difficulty >= 55) return ORANGE;
  return PINK;
}
