import { el } from "../lib/dom.js";

export function notFoundView(outlet) {
  outlet.append(
    el(
      "div",
      { class: "empty" },
      el("h1", {}, "Nothing here"),
      el("p", { class: "muted" }, "That route does not exist."),
      el("a", { class: "btn", href: "/", "data-link": true }, "Back to the dashboard")
    )
  );
}
