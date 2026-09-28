import { el } from "../lib/dom.js";
import { store } from "../lib/store.js";

const UPDATED = "28 September 2026";
const CONTACT = (import.meta.env.VITE_CONTACT_EMAIL || "").trim();

function restoreTitle() {
  document.title = "Piano Pedagogue";
}

function contactLine() {
  if (CONTACT) return el("a", { href: `mailto:${CONTACT}` }, CONTACT);
  return "the support address on the app's store listing";
}

function section(title, ...body) {
  return el("section", { class: "legal-section", id: title.id || null }, el("h2", {}, title.text || title), ...body);
}

function list(items) {
  return el("ul", {}, ...items.map((item) => el("li", {}, ...[].concat(item))));
}

function p(...children) {
  return el("p", {}, ...children);
}

function page(title, intro, sections, other) {
  const back = store.isAuthenticated ? ["/settings", "Back to Settings"] : ["/login", "Back to sign in"];
  return el(
    "article",
    { class: "panel legal" },
    el("p", { class: "faint mono legal-updated" }, `Last updated ${UPDATED}`),
    el("h1", {}, title),
    p(intro),
    ...sections,
    el(
      "div",
      { class: "row legal-links" },
      el("a", { href: back[0], "data-link": true }, back[1]),
      el("a", { href: other[0], "data-link": true }, other[1])
    )
  );
}

export function privacyView(outlet) {
  document.title = "Privacy · Piano Pedagogue";
  outlet.append(
    page(
      "Privacy policy",
      "Pedagogue keeps what it needs to track your repertoire and practice, and nothing else. There are no ads, no tracking across apps or websites, and your data is never sold.",
      [
        section(
          "What we store",
          p("When you create an account and use the app, we store:"),
          list([
            [el("strong", {}, "Account: "), "your email address, an optional display name, and your password as a one-way hash (we never see or store the password itself)."],
            [el("strong", {}, "Profile: "), "years playing, self-assessed level, hand span, time zone, reminder preference, who can see your profile, and whether you appear on leaderboards."],
            [el("strong", {}, "Tastes and technique: "), "the genres, composers and pieces you pick during setup, your technique ratings and tier list."],
            [el("strong", {}, "Repertoire and practice: "), "the pieces you add, their status, tempos, dates and notes, practice sessions and minutes, drills, practice plans, sight-reading and polyrhythm results, performances and readiness scores."],
            [el("strong", {}, "Progress: "), "XP, gold, levels, achievements, cosmetics you buy with in-app gold, streaks, and your daily roulette results."],
            [el("strong", {}, "Friends: "), "friend requests and friendships. Friends can see your constellation if your visibility setting allows it."],
          ]),
          p("We do not collect your location, contacts, photos, advertising identifiers or device identifiers, and we do not use analytics or crash-reporting services.")
        ),
        section(
          "Uploads",
          list([
            "Scores you upload (PDF, MusicXML or MIDI) and recordings you submit are stored privately in encrypted cloud storage, in a folder tied to your account. They are never public and are only read by our servers to analyse them for you.",
            "Only files you choose are uploaded. The app asks the system file picker for one file at a time and never reads your library in the background.",
          ])
        ),
        section(
          "Who else handles your data",
          list([
            "Our hosting and storage providers run the servers, database and file storage on our behalf and may not use your data for anything else.",
            [
              "If AI coach notes are switched on, the piece's title and composer, your tempos, your technique tiers and up to your three most recent practice notes for that piece are sent to Anthropic to write feedback on a recording. Your name, email and the audio itself are not sent. Anthropic does not use this data to train its models.",
            ],
            "When you search for a piece that isn't in our catalogue, your search words are sent to MusicBrainz, the public music encyclopaedia.",
            "The app's fonts are loaded from Google Fonts, which sees your IP address when it serves them.",
          ])
        ),
        section(
          "On your device",
          list([
            "Your sign-in token is kept on your device so you stay signed in.",
            "The app keeps a copy of your repertoire, piece pages and score images on the device so they open without a connection, and holds practice notes written offline until they can be sent. Signing out or deleting your account clears this copy.",
            "The daily practice reminder is scheduled on your device. It is off until you turn it on in Settings, and it never sends data anywhere.",
          ])
        ),
        section(
          { text: "Deleting your account", id: "delete-account" },
          p("You can delete your account at any time, from the app or the website:"),
          el(
            "ol",
            {},
            el("li", {}, "Sign in and open Settings."),
            el("li", {}, "Under Account, choose Delete my account."),
            el("li", {}, "Type DELETE, enter your password, and confirm.")
          ),
          p(
            "This permanently and immediately deletes your account and everything listed above, including every score and recording you uploaded. It cannot be undone. Pieces you added to the shared catalogue stay in the catalogue for other players, but no longer show that you added them. Encrypted database backups kept by our hosting provider roll off within 30 days."
          ),
          p("If you can't sign in, write to ", contactLine(), " from the email address on the account and we will delete it for you within 30 days.")
        ),
        section(
          "Children",
          p("Pedagogue is not directed at children under 13, and we do not knowingly collect their data. If you believe a child under 13 has created an account, contact us and we will delete it.")
        ),
        section(
          "Your rights and contact",
          p(
            "You can see and change most of your data in the app, download your practice history from Settings, and delete everything as described above. For any other request or question about your data, contact ",
            contactLine(),
            ". If this policy changes in a way that matters, we will say so in the app before the change takes effect."
          )
        ),
      ],
      ["/terms", "Terms of use"]
    )
  );
  const anchor = decodeURIComponent(window.location.hash.slice(1));
  if (anchor) requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView({ block: "start" }));
  return restoreTitle;
}

export function termsView(outlet) {
  document.title = "Terms · Piano Pedagogue";
  outlet.append(
    page(
      "Terms of use",
      "These are the rules for using Pedagogue. By creating an account you agree to them.",
      [
        section(
          "Your account",
          list([
            "You need to be at least 13 to use Pedagogue, and old enough in your country to agree to these terms (or have a parent or guardian agree for you).",
            "Keep your password to yourself. You are responsible for what happens on your account.",
            "You can stop using Pedagogue and delete your account at any time from Settings.",
          ])
        ),
        section(
          "What you upload",
          list([
            "Scores, recordings and notes you upload stay yours. You give us permission to store and process them only to run the app for you, for example to analyse a score or write coach notes.",
            "Only upload material you have the right to use. Public-domain scores and your own recordings are always fine.",
            "Pieces you add to the shared catalogue (title, composer and similar details) can be seen and used by other players.",
          ])
        ),
        section(
          "Fair use",
          list([
            "Don't use Pedagogue to harass other players, to break the law, or to try to access other people's accounts or data.",
            "Don't try to disrupt the service, scrape it in bulk, or game leaderboards with automated tools.",
            "We may suspend accounts that break these rules.",
          ])
        ),
        section(
          "XP, gold and cosmetics",
          p("XP, gold and Observatory cosmetics are earned by practising. They have no cash value, cannot be bought, sold or transferred, and may be rebalanced as the app changes.")
        ),
        section(
          "Practice advice",
          p(
            "Difficulty ratings, practice plans, load warnings and coach notes are suggestions to help you practise, not medical or professional advice. Stop and rest if playing hurts, and see a teacher or a health professional about pain or injury."
          )
        ),
        section(
          "The service",
          list([
            "We work to keep Pedagogue running and your data safe, but the app is provided as is, and features may change or be retired.",
            "To the extent the law allows, we are not liable for indirect losses or for losing data you did not keep elsewhere. Nothing here limits rights you have under consumer law.",
            "If these terms change in a way that matters, we will tell you in the app before the change takes effect.",
          ])
        ),
        section("Contact", p("Questions about these terms: ", contactLine(), ".")),
      ],
      ["/privacy", "Privacy policy"]
    )
  );
  return restoreTitle;
}
