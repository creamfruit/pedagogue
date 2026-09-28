import { api } from "../api/client.js";
import { el, openModal, reveal, sectionBlock } from "../lib/dom.js";
import {
  DEFAULT_REMINDER_TIME,
  cancelDailyReminder,
  enableDailyReminder,
  reminderSettings,
  remindersSupported,
} from "../lib/reminders.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";

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
    field("Remind me", select),
    remindersSupported ? dailyReminderControls() : null
  );
}

function dailyReminderControls() {
  const saved = reminderSettings();
  const toggle = el("input", { type: "checkbox", checked: saved.enabled || null });
  const time = el("input", { type: "time", value: saved.time, step: "300", "aria-label": "Reminder time", disabled: !saved.enabled || null });

  async function apply(enable) {
    toggle.disabled = true;
    time.disabled = true;
    try {
      if (!enable) {
        await cancelDailyReminder();
        notify.success("Daily reminder turned off");
        return;
      }
      const result = await enableDailyReminder(time.value || DEFAULT_REMINDER_TIME);
      if (result.ok) {
        notify.success(`You'll get a reminder every day at ${time.value || DEFAULT_REMINDER_TIME}`);
      } else {
        toggle.checked = false;
        notify.error(
          result.reason === "denied"
            ? "Notifications are off for Pedagogue. Allow them in your phone's Settings, then try again."
            : "Choose a time for the reminder"
        );
      }
    } catch (error) {
      toggle.checked = false;
      notify.error(error.message || "Could not set the reminder");
    } finally {
      toggle.disabled = false;
      time.disabled = !toggle.checked;
    }
  }

  toggle.addEventListener("change", () => apply(toggle.checked));
  time.addEventListener("change", () => {
    if (toggle.checked) apply(true);
  });
  return el(
    "div",
    { class: "daily-reminder" },
    el("label", { class: "check-label" }, toggle, "Daily practice reminder on this phone"),
    el("div", { class: "field", style: "margin:var(--space-3) 0 0" }, el("label", {}, "Time"), time),
    el("p", { class: "field-hint" }, "Off until you turn it on. Pedagogue asks for permission to send notifications only then.")
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

function friendRow(item, actions) {
  return el("li", { class: "flat-row" }, el("span", {}, item.name), el("div", { class: "row", style: "gap:var(--space-2)" }, ...actions));
}

function socialSection() {
  const optIn = el("input", { type: "checkbox", checked: store.user?.leaderboard_opt_in || null });
  optIn.addEventListener("change", async () => {
    optIn.disabled = true;
    try {
      store.setUser(await api.updateProfile({ leaderboard_opt_in: optIn.checked }));
      notify.success(optIn.checked ? "You'll appear on leaderboards" : "You're hidden from leaderboards");
    } catch (error) {
      optIn.checked = !optIn.checked;
      notify.error(error.detail || "Could not save that");
    } finally {
      optIn.disabled = false;
    }
  });
  const email = el("input", { type: "email", placeholder: "friend@example.com", "aria-label": "Friend's email" });
  const lists = el("div", { class: "stack", style: "gap:var(--space-3)" });

  async function refresh() {
    try {
      const view = await api.friends();
      const act = (label, run, ghost = true) =>
        el(
          "button",
          {
            type: "button",
            class: `btn btn-small${ghost ? " btn-ghost" : ""}`,
            onclick: async () => {
              try {
                await run();
                await refresh();
              } catch (error) {
                notify.error(error.detail || "That didn't work");
              }
            },
          },
          label
        );
      const block = (title, items, actions) =>
        items.length ? el("div", {}, el("div", { class: "stat-label" }, title), el("ul", { class: "flat-list" }, ...items.map((item) => friendRow(item, actions(item))))) : null;
      lists.replaceChildren(
        ...[
          block("Requests for you", view.incoming, (item) => [act("Accept", () => api.respondFriend(item.id, "accept"), false), act("Decline", () => api.respondFriend(item.id, "decline"))]),
          block("Friends", view.friends, (item) => [act("Remove", () => api.removeFriend(item.id))]),
          block("Waiting for a reply", view.outgoing, (item) => [act("Cancel", () => api.removeFriend(item.id))]),
        ].filter(Boolean)
      );
      if (!lists.children.length) lists.append(el("p", { class: "faint", style: "margin:0;font-size:13px" }, "No friends yet."));
    } catch (error) {
      lists.replaceChildren(el("p", { class: "faint" }, error.detail || "Could not load friends."));
    }
  }

  const send = el(
    "button",
    {
      type: "submit",
      class: "btn btn-small",
      onclick: async (event) => {
        event.preventDefault();
        if (!email.value.trim()) return;
        send.disabled = true;
        try {
          const reply = await api.requestFriend(email.value.trim());
          notify.success(reply.detail);
          email.value = "";
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not send that");
        } finally {
          send.disabled = false;
        }
      },
    },
    "Send request"
  );
  refresh();
  return sectionBlock(
    "Friends & leaderboards",
    { caption: "Friends see each other's constellations (per your visibility setting) and share leaderboards. Nobody appears on a leaderboard unless they opt in." },
    el("label", { class: "check-label", style: "margin-bottom:var(--space-4)" }, optIn, "Show me on leaderboards"),
    el("form", { class: "row", style: "margin-bottom:var(--space-4);flex-wrap:nowrap" }, email, send),
    lists
  );
}

function dataSection() {
  const button = el(
    "button",
    {
      type: "button",
      class: "btn btn-small",
      onclick: async () => {
        button.disabled = true;
        const label = button.textContent;
        button.textContent = "Preparing…";
        try {
          const name = await api.exportTableau();
          notify.success(`Downloaded ${name}`);
        } catch (error) {
          notify.error(error.detail || error.message || "Could not build the export");
        } finally {
          button.disabled = false;
          button.textContent = label;
        }
      },
    },
    "Download for Tableau (.hyper)"
  );
  const tables = [
    ["practice_sessions", "one row per session: start, end, mode, minutes"],
    ["practice_items", "minutes per piece within each session"],
    ["submissions", "recordings and other submissions, with graded scores"],
    ["repertoire", "every piece with its status, difficulty and dates"],
    ["technique_mastery", "your tier and proficiency in each technique"],
    ["wallet_history", "every XP and gold change, with running totals"],
  ];
  const list = reveal("What's in the file", () =>
    el("ul", { class: "flat-list", style: "font-size:13px" }, ...tables.map(([name, what]) => el("li", { class: "flat-row" }, el("span", { class: "mono" }, name), el("span", { class: "faint" }, what))))
  );
  return sectionBlock(
    "Your data",
    { caption: "A Tableau extract of your practice history. Open it in Tableau Desktop or Public (no licence is needed to create the file)." },
    el("div", { style: "margin-bottom:var(--space-3)" }, button),
    list.button,
    list.region
  );
}

const CONFIRM_WORD = "DELETE";

function openDeleteAccount() {
  const typed = el("input", {
    id: "delete-confirm",
    type: "text",
    autocomplete: "off",
    autocapitalize: "characters",
    spellcheck: "false",
    placeholder: CONFIRM_WORD,
  });
  const password = el("input", { id: "delete-password", type: "password", autocomplete: "current-password" });
  const error = el("p", { class: "field-error", role: "alert", hidden: true });
  const submit = el("button", { type: "submit", class: "btn btn-danger", disabled: true }, "Delete my account forever");
  const ready = () => typed.value.trim() === CONFIRM_WORD && password.value.length > 0;
  const sync = () => {
    submit.disabled = !ready();
  };
  typed.addEventListener("input", sync);
  password.addEventListener("input", sync);

  const form = el(
    "form",
    {
      class: "stack delete-account",
      onsubmit: async (event) => {
        event.preventDefault();
        if (!ready()) return;
        error.hidden = true;
        submit.disabled = true;
        submit.textContent = "Deleting…";
        try {
          await api.deleteAccount(password.value);
          modal.close();
          store.signOut();
          notify.success("Your account and all your data have been deleted");
          navigate("/login", { replace: true });
        } catch (failure) {
          error.textContent = failure.detail || "Could not delete the account";
          error.hidden = false;
          submit.textContent = "Delete my account forever";
          sync();
        }
      },
    },
    el("p", { style: "margin:0" }, "This permanently deletes your account and everything in it:"),
    el(
      "ul",
      { class: "delete-account-list" },
      el("li", {}, "your repertoire, practice history, plans and notes"),
      el("li", {}, "every score and recording you uploaded"),
      el("li", {}, "XP, gold, achievements, cosmetics, friends and leaderboard places")
    ),
    el("p", { class: "faint", style: "margin:0" }, "It can't be undone. Download your practice history first under Your data if you want to keep it."),
    el("div", { class: "field" }, el("label", { for: "delete-confirm" }, `Type ${CONFIRM_WORD} to confirm`), typed),
    el("div", { class: "field" }, el("label", { for: "delete-password" }, "Your password"), password),
    error,
    el("div", {}, submit)
  );
  const modal = openModal(form, { title: "Delete my account" });
  typed.focus();
}

function accountSection() {
  return sectionBlock(
    "Account",
    { caption: store.user?.email || "" },
    el(
      "div",
      { class: "row", style: "gap:var(--space-2)" },
      el(
        "button",
        {
          type: "button",
          class: "btn btn-ghost btn-small",
          onclick: () => document.getElementById("sign-out")?.click(),
        },
        "Sign out"
      ),
      el("button", { type: "button", class: "btn btn-danger btn-small", onclick: openDeleteAccount }, "Delete my account")
    ),
    el(
      "p",
      { class: "faint settings-legal" },
      el("a", { href: "/privacy", "data-link": true }, "Privacy policy"),
      " · ",
      el("a", { href: "/terms", "data-link": true }, "Terms of use")
    )
  );
}

export async function settingsView(outlet) {
  const sections = [profileSection(), tiersSection(), remindersSection(), socialSection(), dataSection(), accountSection()];
  outlet.append(
    el("div", { class: "page-head" }, el("h1", { style: "margin:0" }, "Settings")),
    el("div", { class: "settings-stack" }, ...sections.filter(Boolean))
  );
}
