import { api } from "../api/client.js";
import { el, sectionBlock } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";

const LEVELS = [
  ["beginner", "Beginner"],
  ["intermediate", "Intermediate"],
  ["advanced", "Advanced"],
  ["professional", "Professional"],
];
const VISIBILITY = [
  ["private", "Only me"],
  ["friends", "Friends"],
  ["public", "Anyone"],
];

function field(label, control, hint) {
  return el("div", { class: "field" }, el("label", {}, label), control, hint ? el("p", { class: "field-hint" }, hint) : null);
}

function options(pairs, selected) {
  return pairs.map(([value, label]) => el("option", { value, selected: value === selected || null }, label));
}

function profileSection() {
  const user = store.user || {};
  const name = el("input", { type: "text", maxlength: "80", value: user.display_name || "" });
  const level = el("select", {}, el("option", { value: "" }, "Not set"), ...options(LEVELS, user.self_level));
  const years = el("input", { type: "number", min: "0", max: "100", value: user.years_playing ?? "" });
  const span = el("input", { type: "number", min: "10", max: "35", step: "0.5", value: user.hand_span_cm ?? "" });
  const visibility = el("select", {}, ...options(VISIBILITY, user.profile_visibility || "private"));
  const save = el(
    "button",
    {
      type: "submit",
      class: "btn",
      onclick: async (event) => {
        event.preventDefault();
        save.disabled = true;
        try {
          const updated = await api.updateProfile({
            display_name: name.value.trim() || null,
            self_level: level.value || null,
            years_playing: years.value === "" ? null : Number(years.value),
            hand_span_cm: span.value === "" ? null : Number(span.value),
            profile_visibility: visibility.value,
          });
          store.setUser(updated);
          notify.success("Profile saved");
        } catch (error) {
          notify.error(error.detail || "Could not save your profile");
        } finally {
          save.disabled = false;
        }
      },
    },
    "Save profile"
  );
  return sectionBlock(
    "Profile",
    { caption: "Used to personalise difficulty, stretch warnings and what friends can see." },
    el(
      "form",
      { class: "settings-form" },
      field("Display name", name),
      field("Self-assessed level", level),
      field("Years playing", years),
      field("Hand span (cm)", span, "Thumb tip to little-finger tip, stretched. Flags passages wider than you can reach."),
      field("Who can see your profile", visibility),
      el("div", {}, save)
    )
  );
}

const NUDGE_OPTIONS = [
  [0, "Never"],
  [1, "After a day without practice"],
  [2, "After 2 days"],
  [3, "After 3 days"],
  [5, "After 5 days"],
  [7, "After a week"],
  [14, "After two weeks"],
];

function remindersSection() {
  const current = store.user?.nudge_after_days ?? 3;
  const select = el(
    "select",
    { "aria-label": "Practice reminder" },
    ...NUDGE_OPTIONS.map(([value, label]) => el("option", { value, selected: value === current || null }, label))
  );
  select.addEventListener("change", async () => {
    select.disabled = true;
    try {
      store.setUser(await api.updateProfile({ nudge_after_days: Number(select.value) }));
      await store.refreshProfile();
      notify.success(Number(select.value) ? "Reminder saved" : "Reminders turned off");
    } catch (error) {
      notify.error(error.detail || "Could not save that");
    } finally {
      select.disabled = false;
    }
  });
  return sectionBlock(
    "Practice reminders",
    { caption: "A reminder on Today when you haven't logged a practice session for a while. It only appears in the app." },
    field("Remind me", select)
  );
}

function tiersSection() {
  const taken = store.user?.tier_quiz_completed_at;
  return sectionBlock(
    "Technique tiers",
    {
      caption: taken
        ? `Last ranked ${new Date(taken).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}. Your tiers personalise every piece's difficulty.`
        : "Your tiers personalise every piece's difficulty.",
    },
    el("a", { class: "btn btn-small", href: "/settings/tiers", "data-link": true }, "Retake the tier quiz")
  );
}

function accountSection() {
  return sectionBlock(
    "Account",
    { caption: store.user?.email || "" },
    el(
      "button",
      {
        type: "button",
        class: "btn btn-ghost btn-small",
        onclick: () => document.getElementById("sign-out")?.click(),
      },
      "Sign out"
    )
  );
}

export async function settingsView(outlet) {
  const sections = [profileSection(), tiersSection(), remindersSection(), accountSection()];
  outlet.append(
    el("div", { class: "page-head" }, el("h1", { style: "margin:0" }, "Settings")),
    el("div", { class: "settings-stack" }, ...sections.filter(Boolean))
  );
}
