import { CATALOGUE_SOURCES, CREDITS } from "../lib/credits.js";
import { backButton, el } from "../lib/dom.js";
import { store } from "../lib/store.js";

function external(href, text) {
  return el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

function creditSection(credit) {
  return el(
    "section",
    { class: "legal-section credit", id: credit.id },
    el("h2", {}, credit.title),
    el("p", {}, external(credit.url, credit.work), " by ", credit.author, ", licensed under ", external(credit.licenseUrl, credit.license), "."),
    credit.notice ? el("pre", { class: "credit-notice" }, credit.notice.join("\n")) : null,
    el("p", {}, el("strong", {}, "Used for: "), credit.used),
    el("p", {}, el("strong", {}, "Changes: "), credit.changes)
  );
}

export function creditsView(outlet) {
  document.title = "Credits · Piano Pedagogue";
  const back = store.isAuthenticated ? "/settings" : "/login";
  outlet.append(
    backButton(back),
    el(
      "article",
      { class: "panel legal credits" },
      el("h1", {}, "Credits"),
      el("p", {}, "Pedagogue is built on music, recordings and text that their makers share openly. This is who made them and the terms they share them under."),
      ...CREDITS.map(creditSection),
      el(
        "section",
        { class: "legal-section", id: "catalogue" },
        el("h2", {}, "Catalogue data"),
        el(
          "p",
          {},
          "Work titles, catalogue numbers and composers come from ",
          ...CATALOGUE_SOURCES.flatMap((source, index) => [
            index ? (index === CATALOGUE_SOURCES.length - 1 ? " and " : ", ") : "",
            external(source.url, source.name),
            ` (${source.license})`,
          ]),
          "."
        )
      ),
      el(
        "div",
        { class: "row legal-links" },
        el("a", { href: back, "data-link": true }, store.isAuthenticated ? "Back to Settings" : "Back to sign in"),
        el("a", { href: "/privacy", "data-link": true }, "Privacy policy")
      )
    )
  );
  return () => {
    document.title = "Piano Pedagogue";
  };
}
