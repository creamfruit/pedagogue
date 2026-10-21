from __future__ import annotations

from app.core.config import settings
from app.core.plans import FREE, PRO
from app.services.seo import site

CURRENCY_SIGNS = {"usd": "$", "eur": "€", "gbp": "£", "cad": "CA$", "aud": "A$"}
PERIOD_WORDS = {"month": "month", "year": "year"}

DEMO_STEPS = (
    {
        "title": "Pick a piece",
        "text": "Add anything from the catalogue, or your own. Pedagogue scores how hard it is and what makes it hard before you start.",
    },
    {
        "title": "See what is hard",
        "text": "Upload your score and the hardest bars are marked on your own copy, with the technique behind each one.",
    },
    {
        "title": "Practise with a keyboard",
        "text": "Connect a MIDI keyboard. A count-in and metronome set the pace, and every note is checked for pitch, timing and evenness.",
    },
    {
        "title": "Watch it get cleaner",
        "text": "Bars that went wrong light up. Two clean runs raise the tempo a notch, and streaks and reviews keep you coming back.",
    },
)

FEATURES = (
    ("Find the hard bars", "Difficulty, hardest sections and techniques for every piece in the catalogue, and for your own scores."),
    ("Practise with a MIDI keyboard", "Wait-for-me mode, a metronome with a count-in, and a heat strip that shows which bars need work."),
    ("A tempo ladder", "Raise the tempo only after clean runs, so speed never gets ahead of accuracy."),
    ("Streaks and review", "Daily streaks, XP, and reminders to revisit pieces before they fade."),
)


def money(amount: int | None, currency: str | None) -> str:
    if amount is None or not currency:
        return ""
    sign = CURRENCY_SIGNS.get(currency.lower())
    value = f"{amount / 100:,.2f}"
    return f"{sign}{value}" if sign else f"{value} {currency.upper()}"


def pricing_rows() -> list[dict]:
    return [
        {"feature": "Pieces in progress", "free": f"Up to {FREE.active_pieces}", "pro": "Unlimited"},
        {"feature": "Practice tools and the catalogue", "free": "Included", "pro": "Included"},
        {"feature": "Keyboard practice and scoring", "free": "Included", "pro": "Included"},
        {"feature": "Keyboard run history", "free": f"Last {FREE.keyboard_history_attempts} runs", "pro": "Everything"},
        {"feature": "Tempo ladder", "free": f"Up to {round(FREE.tempo_ladder_ceiling * 100)}% of your target", "pro": "All the way to your target"},
        {"feature": "MusicXML and MIDI scores", "free": "Included", "pro": "Included"},
        {"feature": "PDF score reading", "free": "Not included" if not FREE.pdf_score_reading else "Included", "pro": "Included" if PRO.pdf_score_reading else "Not included"},
        {"feature": "Share cards", "free": "Not included" if not FREE.share_cards else "Included", "pro": "Included" if PRO.share_cards else "Not included"},
        {"feature": "Cloud sync", "free": "Not included" if not FREE.cloud_sync else "Included", "pro": "Included" if PRO.cloud_sync else "Not included"},
    ]


def priced(options: list[dict]) -> list[dict]:
    shown = []
    for option in options:
        text = money(option.get("amount"), option.get("currency"))
        if text:
            shown.append({"interval": option["interval"], "text": f"{text} / {PERIOD_WORDS.get(option['interval'], option['interval'])}", "amount": option["amount"], "currency": option["currency"]})
    return shown


def savings_percent(options: list[dict]) -> int:
    by_interval = {option["interval"]: option for option in options if option.get("amount")}
    month, year = by_interval.get("month"), by_interval.get("year")
    if not month or not year:
        return 0
    saved = round((1 - year["amount"] / (month["amount"] * 12)) * 100)
    return saved if saved > 0 else 0


def landing_context(options: list[dict], pieces: int, composers: int) -> dict:
    shown = priced(options)
    return {
        "steps": DEMO_STEPS,
        "features": FEATURES,
        "rows": pricing_rows(),
        "prices": shown,
        "savings": savings_percent(shown),
        "trial_days": settings.stripe_trial_days,
        "checkout_open": settings.stripe_checkout_ready,
        "pieces": pieces,
        "composers": composers,
    }


def landing_seo(context: dict) -> dict:
    url = site("/welcome")
    description = "Pedagogue finds the hard bars in the piano music you are learning, then helps you practise them with a metronome, your MIDI keyboard and a tempo ladder. Free to start."
    offers = [{"@type": "Offer", "name": "Free", "price": "0", "priceCurrency": (context["prices"][0]["currency"] if context["prices"] else "USD").upper()}]
    for price in context["prices"]:
        offers.append(
            {
                "@type": "Offer",
                "name": f"Pro, {price['interval']}ly" if price["interval"] in PERIOD_WORDS else "Pro",
                "price": f"{price['amount'] / 100:.2f}",
                "priceCurrency": price["currency"].upper(),
            }
        )
    return {
        "title": "Pedagogue: practise the hard bars of your piano pieces",
        "description": description,
        "canonical": url,
        "robots": "index, follow",
        "og_type": "website",
        "og_title": "Pedagogue: practise the hard bars of your piano pieces",
        "image": None,
        "jsonld": [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "WebApplication",
                        "name": "Pedagogue",
                        "url": url,
                        "applicationCategory": "EducationalApplication",
                        "operatingSystem": "Web, iOS, Android",
                        "description": description,
                        "offers": offers,
                    },
                    {"@type": "WebSite", "name": "Pedagogue", "url": site("/")},
                ],
            }
        ],
    }
