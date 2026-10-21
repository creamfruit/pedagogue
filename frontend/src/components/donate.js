import { el, sectionBlock } from "../lib/dom.js";
import { DONATION_URL, features } from "../lib/features.js";

export function donationAvailable() {
  return features.paidOffers && Boolean(DONATION_URL);
}

export function donateLink({ label = "Make a donation", className = "btn btn-small btn-ghost" } = {}) {
  if (!donationAvailable()) return null;
  return el("a", { class: className, href: DONATION_URL, target: "_blank", rel: "noopener noreferrer", "data-donate": "" }, label);
}

export function supportSection() {
  const link = donateLink();
  if (!link) return null;
  return sectionBlock(
    "Support Pedagogue",
    { caption: "The Free plan stays free. If Pedagogue helps your practice and you'd rather not subscribe, you can chip in towards hosting." },
    link
  );
}

export function donateNote() {
  const link = donateLink({ label: "Chip in instead", className: "" });
  if (!link) return null;
  return el("p", { class: "faint plan-note donate-note" }, "Not after Pro? A one-off donation towards hosting is always welcome. ", link, ".");
}
