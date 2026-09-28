import { isAndroid, isIOS } from "./platform.js";

export const SCORE_EXTENSIONS = [".pdf", ".musicxml", ".xml", ".mxl", ".mid", ".midi"];
const SCORE_TYPES = [
  "application/pdf",
  "application/vnd.recordare.musicxml+xml",
  "application/vnd.recordare.musicxml",
  "application/xml",
  "text/xml",
  "audio/midi",
  "audio/x-midi",
];

export function scoreAccept() {
  if (isAndroid) return null;
  if (isIOS) return [...SCORE_EXTENSIONS, "application/pdf"].join(",");
  return [...SCORE_EXTENSIONS, ...SCORE_TYPES].join(",");
}

export function isScoreFile(file) {
  const name = (file?.name || "").toLowerCase();
  if (SCORE_EXTENSIONS.some((extension) => name.endsWith(extension))) return true;
  return SCORE_TYPES.includes((file?.type || "").toLowerCase());
}
