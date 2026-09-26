import { el, tabs } from "../lib/dom.js";
import { navigate } from "../router.js";
import { growthView } from "./growth.js";
import { performancesView } from "./performances.js";
import { progressionView } from "./progression.js";

const TABS = [
  {
    id: "growth",
    label: "Growth",
    caption: "Your practice streak and how the difficulty of what you play is changing.",
    render: (host) => growthView(host),
  },
  {
    id: "pathways",
    label: "Pathways",
    caption: "Pick a piece you want to play and the engine works backwards from it.",
    render: (host) => progressionView(host, { embedded: true }),
  },
  {
    id: "performances",
    label: "Performances",
    caption: "Recitals and exams you're preparing for, and how ready each programme is.",
    render: (host) => performancesView(host, { embedded: true }),
  },
];

function initialTab(context) {
  if (context.pathname === "/performances") return "performances";
  if (context.pathname === "/progression") return "pathways";
  const wanted = context.query?.tab;
  return TABS.some((tab) => tab.id === wanted) ? wanted : TABS[0].id;
}

export async function progressView(outlet, context) {
  const active = initialTab(context);
  const current = TABS.find((tab) => tab.id === active);
  const caption = el("p", { class: "muted", style: "margin:4px 0 0" }, current.caption);
  const host = el("div", { class: "tab-panel" });
  const strip = tabs(
    TABS.map((tab) => ({ id: tab.id, label: tab.label })),
    active,
    (id) => navigate(id === TABS[0].id ? "/progress" : `/progress?tab=${id}`, { replace: true }),
    { label: "Progress sections", controls: "progress-panel" }
  );
  host.id = "progress-panel";
  host.setAttribute("role", "tabpanel");
  if (active === "pathways") {
    caption.append(" ", el("a", { href: "/settings/tiers", "data-link": true }, "Retake the tier quiz"), " if your strengths have changed.");
  }
  outlet.append(el("div", { class: "page-head" }, el("div", {}, el("h1", { style: "margin:0" }, "Progress"), caption)), strip, host);
  await current.render(host);
}
