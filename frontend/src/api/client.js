const PREFIX = import.meta.env.VITE_API_PREFIX || "/api/v1";
const ORIGIN = import.meta.env.DEV ? "" : import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "pp.token";

export class ApiError extends Error {
  constructor(status, detail, payload) {
    super(detail || `request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }

  get isAuth() {
    return this.status === 401 || this.status === 403;
  }

  get isConflict() {
    return this.status === 409;
  }

  get isOffline() {
    return this.status === 0;
  }
}

export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable */
    }
  },
};

const listeners = new Set();

export function onUnauthorized(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function notifyUnauthorized() {
  listeners.forEach((handler) => handler());
}

function buildUrl(path, params) {
  const base = path.startsWith("http") ? path : `${ORIGIN}${PREFIX}${path}`;
  if (!params) return base;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.append(key, String(value));
  });
  const query = search.toString();
  return query ? `${base}?${query}` : base;
}

async function parse(response) {
  const type = response.headers.get("content-type") || "";
  if (response.status === 204) return null;
  if (type.includes("application/json")) return response.json();
  return response.text();
}

function extractDetail(payload, status) {
  if (!payload) return `request failed with ${status}`;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.errors) && payload.errors.length) {
    const first = payload.errors[0];
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "field";
    return `${field}: ${first.msg}`;
  }
  if (Array.isArray(payload.detail) && payload.detail.length) {
    const first = payload.detail[0];
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "field";
    return `${field}: ${first.msg}`;
  }
  return `request failed with ${status}`;
}

export async function request(path, { method = "GET", body, params, form, signal, auth = true } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(buildUrl(path, params), { method, headers, body: payload, signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "you appear to be offline");
  }

  const data = await parse(response);
  if (!response.ok) {
    if (response.status === 401) {
      tokenStore.clear();
      notifyUnauthorized();
    }
    throw new ApiError(response.status, extractDetail(data, response.status), data);
  }
  return data;
}

export const api = {
  get: (path, params, options) => request(path, { ...options, params }),
  post: (path, body, options) => request(path, { ...options, method: "POST", body }),
  put: (path, body, options) => request(path, { ...options, method: "PUT", body }),
  patch: (path, body, options) => request(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => request(path, { ...options, method: "DELETE" }),
  upload: (path, form, options) => request(path, { ...options, method: "POST", form }),

  register: (payload) => request("/auth/register", { method: "POST", body: payload, auth: false }),
  login: (email, password) =>
    request("/auth/token", { method: "POST", body: { email, password }, auth: false }),
  me: () => request("/auth/me"),

  onboardingStatus: () => request("/onboarding/status"),
  onboardingSummary: () => request("/onboarding/summary"),
  updateProfile: (payload) => request("/onboarding/profile", { method: "PUT", body: payload }),
  updateGenres: (genreIds) => request("/onboarding/genres", { method: "PUT", body: { genre_ids: genreIds } }),
  updateComposers: (composers) => request("/onboarding/composers", { method: "PUT", body: { composers } }),
  updateTechniqueProfiles: (techniques) =>
    request("/onboarding/techniques", { method: "PUT", body: { techniques } }),
  updateTierList: (tiers) => request("/onboarding/tier-list", { method: "PUT", body: { tiers } }),
  updateTopTen: (pieces) => request("/onboarding/top-ten", { method: "PUT", body: { pieces } }),

  searchPieces: (q, limit = 20) => request("/catalog/pieces", { params: { q, limit } }),
  createPiece: (payload) => request("/catalog/pieces", { method: "POST", body: payload }),
  searchExternalCatalog: (q, limit = 15) => request("/catalog/external/search", { params: { q, limit } }),
  importExternalPiece: (payload) => request("/catalog/external/import", { method: "POST", body: payload }),
  piece: (id) => request(`/catalog/pieces/${id}`),
  pieceOverview: (id) => request(`/catalog/pieces/${id}/overview`),
  linkSummary: (sourceId, targetId, linkType) =>
    request(`/catalog/links/${sourceId}/${targetId}`, { params: { link_type: linkType } }),
  searchComposers: (q) => request("/catalog/composers", { params: { q } }),
  passageSightReading: (passageId, techniqueId) =>
    request(`/catalog/passages/${passageId}/sight-reading`, { params: techniqueId ? { technique_id: techniqueId } : undefined }),
  genres: () => request("/catalog/genres"),
  techniques: () => request("/catalog/techniques"),
  techniqueExamples: () => request("/catalog/techniques/examples"),

  repertoire: (params) => request("/repertoire", { params }),
  repertoireStats: () => request("/repertoire/stats"),
  createEntry: (payload) => request("/repertoire", { method: "POST", body: payload }),
  entry: (id) => request(`/repertoire/${id}`),
  updateEntry: (id, payload) => request(`/repertoire/${id}`, { method: "PATCH", body: payload }),
  deleteEntry: (id) => request(`/repertoire/${id}`, { method: "DELETE" }),
  maintenanceRun: (id) => request(`/repertoire/${id}/maintenance-run`, { method: "POST" }),

  submissions: (entryId) => request(`/repertoire/${entryId}/submissions`),
  submitText: (entryId, bodyText) =>
    request(`/repertoire/${entryId}/submissions/text`, { method: "POST", body: { body: bodyText } }),
  submitPdf: (entryId, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/repertoire/${entryId}/submissions/pdf`, { method: "POST", form });
  },
  submitAudio: (entryId, file, { durationSec, isFullRunThrough, isVerification } = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (durationSec != null) form.append("duration_sec", String(Math.round(durationSec)));
    form.append("is_full_run_through", isFullRunThrough ? "true" : "false");
    form.append("is_verification", isVerification ? "true" : "false");
    return request(`/repertoire/${entryId}/submissions/audio`, { method: "POST", form });
  },
  submission: (id) => request(`/submissions/${id}`),
  analyses: (id) => request(`/submissions/${id}/analyses`),
  retrySubmission: (id) => request(`/submissions/${id}/retry`, { method: "POST" }),

  prerequisites: (pieceId, params) => request(`/progression/pieces/${pieceId}/prerequisites`, { params }),
  pathway: (pieceId, params) => request(`/progression/pieces/${pieceId}/pathway`, { params }),
  adoptPathway: (pieceId, body) =>
    request(`/progression/pieces/${pieceId}/pathway/adopt`, { method: "POST", body: body || { include_target: true } }),
  steppingStones: (pieceId, params) => request(`/progression/pieces/${pieceId}/path`, { params }),
  recommendations: (params) => request("/progression/recommendations", { params }),
  decideRecommendation: (id, status) =>
    request(`/progression/recommendations/${id}`, { method: "PATCH", body: { status } }),
  constellation: (params) => request("/progression/constellation", { params }),
  friendConstellation: (friendId, params) =>
    request(`/progression/constellation/${friendId}`, { params }),

  startSession: (payload) => request("/practice/sessions", { method: "POST", body: payload }),
  sessions: (params) => request("/practice/sessions", { params }),
  openSession: () => request("/practice/sessions/open"),
  addSessionItem: (id, payload) =>
    request(`/practice/sessions/${id}/items`, { method: "POST", body: payload }),
  closeSession: (id, payload) =>
    request(`/practice/sessions/${id}/close`, { method: "POST", body: payload || {} }),
  load: (params) => request("/practice/load", { params }),
  loadAlerts: () => request("/practice/load/alerts"),
  acknowledgeAlert: (id) => request(`/practice/load/alerts/${id}/acknowledge`, { method: "POST" }),

  drills: () => request("/drills"),
  forgeDrills: (payload) => request("/drills/forge", { method: "POST", body: payload }),
  deleteDrill: (id) => request(`/drills/${id}`, { method: "DELETE" }),
  buildPlan: (entryId) => request(`/repertoire/${entryId}/plans`, { method: "POST" }),
  plans: (entryId) => request(`/repertoire/${entryId}/plans`),
  advanceStep: (planId, stepId) =>
    request(`/plans/${planId}/steps/${stepId}/advance`, { method: "POST" }),
  generateSightReading: (payload) => request("/sight-reading", { method: "POST", body: payload || {} }),
  sightReading: () => request("/sight-reading"),
  scoreSightReading: (id, selfScore) =>
    request(`/sight-reading/${id}/score`, { method: "POST", body: { self_score: selfScore } }),
  recordPolyrhythm: (payload) => request("/polyrhythm/attempts", { method: "POST", body: payload }),
  polyrhythmStats: () => request("/polyrhythm/stats"),

  performances: (params) => request("/performances", { params }),
  createPerformance: (payload) => request("/performances", { method: "POST", body: payload }),
  performance: (id) => request(`/performances/${id}`),
  setProgram: (id, entryIds) =>
    request(`/performances/${id}/program`, { method: "PUT", body: { repertoire_entry_ids: entryIds } }),
  performanceReadiness: (id) => request(`/performances/${id}/readiness`),
  scoreReadiness: (entryId) => request(`/repertoire/${entryId}/readiness`, { method: "POST" }),
  gate: (entryId) => request(`/repertoire/${entryId}/gate`),

  wallet: () => request("/wallet"),
  ledger: (limit = 40) => request("/wallet/ledger", { params: { limit } }),
  achievements: () => request("/achievements"),
  shop: () => request("/shop"),
  buyCosmetic: (id) => request(`/shop/${id}/buy`, { method: "POST" }),
  equipCosmetic: (id) => request(`/shop/${id}/equip`, { method: "POST" }),
  loadout: () => request("/loadout"),
  profileSummary: () => request("/profile/summary"),
  readinessHistory: (entryId) => request(`/repertoire/${entryId}/readiness`),
};

export function liveSocketUrl(targetBpm) {
  const token = tokenStore.get();
  const base = ORIGIN || window.location.origin;
  const url = new URL(`${PREFIX}/practice/live`, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (token) url.searchParams.set("token", token);
  if (targetBpm) url.searchParams.set("target_bpm", String(targetBpm));
  return url.toString();
}

export async function pollSubmission(id, { interval = 1200, attempts = 25, onTick } = {}) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const submission = await api.submission(id);
    if (onTick) onTick(submission, attempt);
    if (submission.processing_status === "done" || submission.processing_status === "failed") {
      return submission;
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  throw new ApiError(408, "analysis is taking longer than expected, check back shortly");
}
