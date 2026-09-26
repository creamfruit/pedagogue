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
  const sections = [profileSection(), accountSection()];
  outlet.append(
    el("div", { class: "page-head" }, el("h1", { style: "margin:0" }, "Settings")),
    el("div", { class: "settings-stack" }, ...sections.filter(Boolean))
  );
}
