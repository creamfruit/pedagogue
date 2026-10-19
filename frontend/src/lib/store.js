import { api, forgetOfflineData, tokenStore } from "../api/client.js";
import { lightTap } from "./haptics.js";
import { cancelDailyReminder } from "./reminders.js";

const state = {
  user: null,
  onboarding: null,
  wallet: null,
  loadout: null,
  streak: null,
  nudge: null,
  ready: false,
  serverDown: false,
};

const subscribers = new Set();

export function subscribe(handler) {
  subscribers.add(handler);
  return () => subscribers.delete(handler);
}

function emit() {
  subscribers.forEach((handler) => handler(state));
}

let lastAchievements = null;

function celebrate(summary) {
  const earned = summary.achievements_earned ?? null;
  const streakCompleted = Boolean(state.streak && !state.streak.today_done && summary.streak?.today_done);
  const unlocked = lastAchievements !== null && earned !== null && earned > lastAchievements;
  if (earned !== null) lastAchievements = earned;
  if (streakCompleted || unlocked) lightTap();
}

async function loadProfile() {
  try {
    const summary = await api.profileSummary();
    celebrate(summary);
    state.wallet = summary.wallet;
    state.loadout = summary.loadout;
    state.streak = summary.streak || null;
    state.nudge = summary.nudge || null;
  } catch {
    state.wallet = null;
    state.loadout = null;
    state.streak = null;
    state.nudge = null;
  }
}

async function loadOnboarding() {
  try {
    state.onboarding = await api.onboardingStatus();
  } catch {
    state.onboarding = null;
  }
}

export const store = {
  get user() {
    return state.user;
  },
  get onboarding() {
    return state.onboarding;
  },
  get wallet() {
    return state.wallet;
  },
  get loadout() {
    return state.loadout;
  },
  get streak() {
    return state.streak;
  },
  get nudge() {
    return state.nudge;
  },
  get ready() {
    return state.ready;
  },
  get serverDown() {
    return state.serverDown;
  },
  get isAuthenticated() {
    return Boolean(state.user);
  },
  async hydrate() {
    if (!tokenStore.get()) {
      state.user = null;
      state.ready = true;
      emit();
      return null;
    }
    state.serverDown = false;
    for (let attempt = 0; attempt < 6; attempt += 1) {
      try {
        state.user = await api.me();
        await Promise.all([loadProfile(), loadOnboarding()]);
        break;
      } catch (error) {
        state.user = null;
        if (error && (error.status === 401 || error.status === 403)) {
          tokenStore.clear();
          break;
        }
        if (error?.isOffline) break;
        if (attempt === 5) {
          state.serverDown = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 600 * (attempt + 1)));
      }
    }
    const refreshed = state.user ? await api.refreshToken().catch(() => null) : null;
    if (refreshed?.access_token) tokenStore.set(refreshed.access_token);
    state.ready = true;
    emit();
    return state.user;
  },
  async signIn(email, password) {
    const token = await api.login(email, password);
    tokenStore.set(token.access_token);
    state.user = await api.me();
    await Promise.all([loadProfile(), loadOnboarding()]);
    emit();
    return state.user;
  },
  async signUp(payload) {
    const token = await api.register(payload);
    tokenStore.set(token.access_token);
    state.user = await api.me();
    await Promise.all([loadProfile(), loadOnboarding()]);
    emit();
    return state.user;
  },
  signOut() {
    tokenStore.clear();
    forgetOfflineData();
    cancelDailyReminder({ forget: true });
    lastAchievements = null;
    state.user = null;
    state.onboarding = null;
    state.wallet = null;
    state.loadout = null;
    state.streak = null;
    state.nudge = null;
    emit();
  },
  async refreshProfile() {
    if (!state.user) return null;
    await loadProfile();
    emit();
    return state.wallet;
  },
  async refreshOnboarding() {
    if (!state.user) return null;
    await loadOnboarding();
    emit();
    return state.onboarding;
  },
  setUser(user) {
    state.user = user;
    emit();
  },
};
