export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === false) return;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  });
  children.flat().forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return node;
}

let disclosureCount = 0;

export function disclosure(trigger, { label, buttonClass = "disclosure-btn", regionClass = "disclosure-region", onFirstOpen, onClose } = {}) {
  disclosureCount += 1;
  const id = `disclosure-${disclosureCount}`;
  const region = el("div", { id, class: regionClass, hidden: true });
  let opened = false;
  const button = el(
    "button",
    {
      type: "button",
      class: buttonClass,
      "aria-expanded": "false",
      "aria-controls": id,
      "aria-label": label,
      title: label,
    },
    trigger
  );
  function toggle(force) {
    const open = force ?? region.hidden;
    region.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open && !opened) {
      opened = true;
      if (onFirstOpen) onFirstOpen(region);
    }
    if (!open && onClose) onClose(region);
  }
  button.addEventListener("click", () => toggle());
  return { button, region, toggle };
}

export function reveal(label, fill, { open = false, onClose } = {}) {
  const control = disclosure(label, {
    buttonClass: "reveal-btn",
    regionClass: "reveal-region",
    onFirstOpen: (region) => {
      const content = typeof fill === "function" ? fill() : fill;
      region.append(...[].concat(content).filter(Boolean));
    },
    onClose,
  });
  if (open) control.toggle(true);
  return control;
}

export function sectionBlock(title, { caption, action, className = "" } = {}, ...children) {
  return el(
    "section",
    { class: `panel detail-section ${className}`.trim() },
    el(
      "div",
      { class: "section-head" },
      el("div", {}, el("h2", { class: "section-title" }, title), caption ? el("p", { class: "section-caption" }, caption) : null),
      action || null
    ),
    ...children
  );
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function panel(title, ...children) {
  return el("section", { class: "panel" }, title ? el("h3", {}, title) : null, ...children);
}

export function ringStat(label, value) {
  return el(
    "div",
    { class: "panel", style: "display:flex;align-items:center;gap:16px" },
    el("div", { class: "stat-ring" }, el("div", { class: "stat" }, value)),
    el("div", {}, el("div", { class: "stat-label" }, label))
  );
}

export function skeletonBlock(rows = 3) {
  return el(
    "div",
    { class: "stack" },
    ...Array.from({ length: rows }, (_, index) =>
      el("div", { class: "skeleton", style: `width:${100 - index * 12}%` })
    )
  );
}

export function empty(message, action) {
  return el("div", { class: "empty" }, el("p", {}, message), action || null);
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "--:--";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export function openModal(contentNode, { title } = {}) {
  let closed = false;
  const overlay = el("div", { class: "modal-overlay" });
  const box = el(
    "div",
    { class: "modal" },
    el(
      "div",
      { class: "row", style: "justify-content:space-between;margin-bottom:14px" },
      el("h2", { style: "margin:0" }, title || ""),
      el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => close() }, "Close")
    ),
    contentNode
  );
  overlay.append(box);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  function onKey(event) {
    if (event.key === "Escape") close();
  }
  function close() {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey);
    overlay.remove();
  }
  document.addEventListener("keydown", onKey);
  document.body.append(overlay);
  return { close };
}

export function optionCard({ icon, title, description, onSelect }) {
  return el(
    "button",
    { type: "button", class: "option-card", onclick: onSelect },
    el("span", { class: "option-icon" }, icon),
    el("div", {}, el("strong", { style: "font-weight:500" }, title), el("p", { class: "faint", style: "margin:4px 0 0;font-size:12px" }, description))
  );
}

export function toneForSeverity(severity) {
  if (severity === "rest") return "pill-bad";
  if (severity === "caution") return "pill-warn";
  return "pill-ok";
}
