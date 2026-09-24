import { el } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";

function field(label, input, errorId) {
  return el("div", { class: "field" }, el("label", { for: input.id }, label), input, el("p", { class: "field-error", id: errorId, hidden: true }));
}

function showError(id, message) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
}

export function loginView(outlet) {
  const email = el("input", { id: "email", type: "email", autocomplete: "email", placeholder: "you@example.com" });
  const password = el("input", { id: "password", type: "password", autocomplete: "current-password", placeholder: "your password" });
  const submit = el("button", { class: "btn", type: "submit" }, "Sign in");

  const form = el(
    "form",
    {
      class: "panel panel-accent form-narrow",
      onsubmit: async (event) => {
        event.preventDefault();
        showError("email-error", "");
        showError("password-error", "");
        if (!email.value.trim()) return showError("email-error", "Enter your email");
        if (!password.value) return showError("password-error", "Enter your password");
        submit.disabled = true;
        submit.textContent = "Signing in";
        try {
          await store.signIn(email.value.trim(), password.value);
          await store.refreshOnboarding();
          notify.success(`Welcome back, ${store.user.display_name || "pianist"}`);
          navigate("/");
        } catch (error) {
          showError("password-error", error.detail || "Could not sign in");
          submit.disabled = false;
          submit.textContent = "Sign in";
        }
      },
    },
    el("h1", {}, "Sign in"),
    el("p", { class: "muted" }, "Your repertoire, your weaknesses, your route to the next piece."),
    field("Email", email, "email-error"),
    field("Password", password, "password-error"),
    el("div", { class: "row", style: "justify-content:space-between;margin-top:6px" }, submit, el("a", { href: "/register", "data-link": true, class: "muted" }, "Create an account"))
  );

  outlet.append(form);
  email.focus();
}

export function registerView(outlet) {
  const name = el("input", { id: "name", type: "text", autocomplete: "name", placeholder: "Sean" });
  const email = el("input", { id: "email", type: "email", autocomplete: "email", placeholder: "you@example.com" });
  const password = el("input", { id: "password", type: "password", autocomplete: "new-password", placeholder: "at least 8 characters" });
  const submit = el("button", { class: "btn", type: "submit" }, "Create account");

  const form = el(
    "form",
    {
      class: "panel panel-accent form-narrow",
      onsubmit: async (event) => {
        event.preventDefault();
        showError("email-error", "");
        showError("password-error", "");
        if (!email.value.trim()) return showError("email-error", "Enter your email");
        if (password.value.length < 8) return showError("password-error", "Use at least 8 characters");
        if (/^[a-zA-Z]+$/.test(password.value) || /^\d+$/.test(password.value)) {
          return showError("password-error", "Mix letters and numbers");
        }
        submit.disabled = true;
        submit.textContent = "Creating";
        try {
          await store.signUp({
            email: email.value.trim(),
            password: password.value,
            display_name: name.value.trim() || null,
          });
          await store.refreshOnboarding();
          notify.success("Account created");
          navigate("/");
        } catch (error) {
          showError("email-error", error.detail || "Could not create the account");
          submit.disabled = false;
          submit.textContent = "Create account";
        }
      },
    },
    el("h1", {}, "Create your account"),
    field("Display name", name, "name-error"),
    field("Email", email, "email-error"),
    field("Password", password, "password-error"),
    el("div", { class: "row", style: "justify-content:space-between;margin-top:6px" }, submit, el("a", { href: "/login", "data-link": true, class: "muted" }, "I already have one"))
  );

  outlet.append(form);
  name.focus();
}
