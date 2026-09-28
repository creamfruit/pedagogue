import { isNative } from "./platform.js";

const KEY = "pp.reminder";
const NOTIFICATION_ID = 4101;
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

export const DEFAULT_REMINDER_TIME = "18:30";
export const remindersSupported = isNative;

export function reminderSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "null");
    return {
      enabled: Boolean(saved?.enabled),
      time: TIME_PATTERN.test(saved?.time || "") ? saved.time : DEFAULT_REMINDER_TIME,
    };
  } catch {
    return { enabled: false, time: DEFAULT_REMINDER_TIME };
  }
}

function save(settings) {
  try {
    if (settings) localStorage.setItem(KEY, JSON.stringify(settings));
    else localStorage.removeItem(KEY);
  } catch {
    return false;
  }
  return true;
}

function loadPlugin() {
  return import("@capacitor/local-notifications").then((module) => module.LocalNotifications);
}

async function allowed(LocalNotifications) {
  let status = await LocalNotifications.checkPermissions();
  if (status.display === "prompt" || status.display === "prompt-with-rationale") {
    status = await LocalNotifications.requestPermissions();
  }
  return status.display === "granted";
}

async function schedule(LocalNotifications, time) {
  const [hour, minute] = time.split(":").map(Number);
  await LocalNotifications.cancel({ notifications: [{ id: NOTIFICATION_ID }] });
  await LocalNotifications.schedule({
    notifications: [
      {
        id: NOTIFICATION_ID,
        title: "Time to practise",
        body: "A few focused minutes at the piano keeps your streak going.",
        schedule: { on: { hour, minute }, allowWhileIdle: true },
        smallIcon: "ic_stat_pedagogue",
        iconColor: "#6fb7b3",
        isExactNotification: false,
      },
    ],
  });
}

export async function enableDailyReminder(time) {
  if (!isNative) return { ok: false, reason: "unsupported" };
  if (!TIME_PATTERN.test(time)) return { ok: false, reason: "time" };
  const LocalNotifications = await loadPlugin();
  if (!(await allowed(LocalNotifications))) return { ok: false, reason: "denied" };
  await schedule(LocalNotifications, time);
  save({ enabled: true, time });
  return { ok: true };
}

export async function cancelDailyReminder({ forget = false } = {}) {
  if (forget) save(null);
  else save({ ...reminderSettings(), enabled: false });
  if (!isNative) return;
  try {
    const LocalNotifications = await loadPlugin();
    await LocalNotifications.cancel({ notifications: [{ id: NOTIFICATION_ID }] });
  } catch {
    return;
  }
}
