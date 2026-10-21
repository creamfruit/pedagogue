from __future__ import annotations

from typing import Optional
from xml.sax.saxutils import escape

from app.core.config import settings
from app.services.public_pages import trimmed

SUFFIX = " · Pedagogue"
TITLE_LIMIT = 65
DESCRIPTION_LIMIT = 155
SITE_NAME = "Pedagogue"


def site(path: str = "/") -> str:
    return f"{settings.return_base_url}{path}"


def fit_title(main: str, suffix: str = SUFFIX, limit: int = TITLE_LIMIT) -> str:
    if len(main) + len(suffix) <= limit:
        return f"{main}{suffix}"
    return trimmed(main, limit)


def year_text(value: Optional[int]) -> Optional[str]:
    return str(value) if value else None


def iso_duration(seconds: Optional[int]) -> Optional[str]:
    if not seconds:
        return None
    minutes, rest = divmod(int(seconds), 60)
    return f"PT{minutes}M{rest}S" if minutes else f"PT{rest}S"


def person(composer, slug: str) -> dict:
    data = {"@type": "Person", "name": composer.name, "url": site(f"/composers/{slug}")}
    if composer.birth_year:
        data["birthDate"] = str(composer.birth_year)
    if composer.death_year:
        data["deathDate"] = str(composer.death_year)
    if composer.nationality:
        data["nationality"] = composer.nationality
    return data


def breadcrumbs(trail: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": url}
            for index, (name, url) in enumerate(trail, start=1)
        ],
    }


def piece_questions(page: dict) -> list[tuple[str, str]]:
    title = page["title"]
    difficulty = page["difficulty"]
    grade = f", about the level of {difficulty['grade']}" if difficulty["grade"] and difficulty["grade"] != "Unrated" else ""
    questions = [
        (
            f"How hard is {title}?",
            f"{title} is {difficulty['band_phrase']}{grade}. It scores {difficulty['score']} out of 100 on Pedagogue's difficulty scale.",
        )
    ]
    if page["sections"]:
        names = "; ".join(f"{section['label'] or 'bars ' + str(section['start_measure']) + '-' + str(section['end_measure'])} ({section['measure_span']})" for section in page["sections"][:3])
        questions.append((f"Which sections of {title} are hardest?", f"The hardest sections are {names}."))
    if page["techniques"]:
        names = ", ".join(technique["name"] for technique in page["techniques"][:5])
        questions.append((f"Which techniques does {title} use?", f"It uses {names}."))
    story = page["story"]
    if story["history"]:
        questions.append((f"What is the story behind {title}?", trimmed(story["history"], 400)))
    if page["similar"]:
        questions.append((f"What pieces are similar to {title}?", "Similar pieces include " + ", ".join(item["full_title"] for item in page["similar"][:4]) + "."))
    return questions


def piece_description(page: dict) -> str:
    difficulty = page["difficulty"]
    lead = f"{page['full_title']} is {difficulty['band_phrase']} (difficulty {difficulty['score']}/100)."
    if page["techniques"]:
        lead += " Techniques: " + ", ".join(technique["name"] for technique in page["techniques"][:3]) + "."
    return trimmed(lead + " See its hardest sections, the story behind it and similar pieces.", DESCRIPTION_LIMIT)


def piece_seo(page: dict) -> dict:
    url = site(f"/music/{page['slug']}")
    composer = page["composer"]
    work: dict = {
        "@type": "MusicComposition",
        "@id": f"{url}#work",
        "name": page["title"],
        "url": url,
        "description": piece_description(page),
        "additionalProperty": {
            "@type": "PropertyValue",
            "name": "Pedagogue difficulty score",
            "value": page["difficulty"]["score"],
            "minValue": 0,
            "maxValue": 100,
        },
    }
    if composer:
        work["composer"] = person(composer, page["composer_slug"])
    if page["key"]:
        work["musicalKey"] = page["key"]
    if page["year"]:
        work["dateCreated"] = str(page["year"])
    if page["genre"]:
        work["genre"] = page["genre"]
    if page["piece"].catalog_number:
        work["identifier"] = page["piece"].catalog_number
    if page["parent"] and page["parent"]["listed"]:
        work["isPartOf"] = {"@type": "MusicComposition", "name": page["parent"]["title"], "url": site(f"/music/{page['parent']['slug']}")}
    movements = [movement for movement in page["movements"] if movement["listed"]]
    if movements:
        work["hasPart"] = [{"@type": "MusicComposition", "name": movement["title"], "url": site(f"/music/{movement['slug']}")} for movement in movements]
    trail = [("Music", site("/music"))]
    if composer:
        trail.append((composer.name, site(f"/composers/{page['composer_slug']}")))
    trail.append((page["title"], url))
    faq = {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}}
            for question, answer in piece_questions(page)
        ],
    }
    title = fit_title(f"{page['full_title']}: how hard is it?")
    description = piece_description(page)
    return {
        "title": title,
        "description": description,
        "canonical": url,
        "robots": "index, follow",
        "og_type": "article",
        "og_title": fit_title(f"{page['full_title']}: how hard is it?", "", 90),
        "image": site(f"/music/{page['slug']}/card.png"),
        "jsonld": [{"@context": "https://schema.org", "@graph": [work, breadcrumbs(trail), faq]}],
    }


def composer_seo(page: dict) -> dict:
    composer = page["composer"]
    url = site(f"/composers/{page['slug']}")
    works = page["works"]
    description_parts = [f"{composer.name}{' (' + composer.lifespan + ')' if composer.lifespan else ''}: how hard are the {len(works)} piano piece{'' if len(works) == 1 else 's'} in the catalogue?"]
    if works:
        description_parts.append(f"From {works[0]['title']} to {works[-1]['title']}.")
    description = trimmed(" ".join(description_parts) + " Difficulty, hardest sections and techniques.", DESCRIPTION_LIMIT)
    data = person(composer, page["slug"])
    if composer.bio:
        data["description"] = trimmed(composer.bio, 300)
    data["@id"] = f"{url}#composer"
    listing = {
        "@type": "ItemList",
        "name": f"Piano pieces by {composer.name}",
        "itemListElement": [{"@type": "ListItem", "position": index, "name": work["title"], "url": site(f"/music/{work['slug']}")} for index, work in enumerate(works, start=1)],
    }
    return {
        "title": fit_title(f"{composer.name}: how hard are the piano pieces?"),
        "description": description,
        "canonical": url,
        "robots": "index, follow",
        "og_type": "profile",
        "og_title": f"{composer.name} · piano pieces and how hard they are",
        "image": None,
        "jsonld": [{"@context": "https://schema.org", "@graph": [data, listing, breadcrumbs([("Composers", site("/composers")), (composer.name, url)])]}],
    }


def listing_seo(count: int, composers: int) -> dict:
    url = site("/music")
    return {
        "title": fit_title("Piano pieces and how hard they are"),
        "description": trimmed(f"{count} piano pieces by {composers} composers, each with a difficulty score, its hardest sections, the techniques it uses and the story behind it.", DESCRIPTION_LIMIT),
        "canonical": url,
        "robots": "index, follow",
        "og_type": "website",
        "og_title": "Piano pieces and how hard they are",
        "image": None,
        "jsonld": [{"@context": "https://schema.org", "@graph": [{"@type": "CollectionPage", "name": "Piano pieces and how hard they are", "url": url}, breadcrumbs([("Music", url)])]}],
    }


def composers_seo(groups: list[dict]) -> dict:
    url = site("/composers")
    return {
        "title": fit_title("Piano composers and their pieces"),
        "description": trimmed(f"{len(groups)} composers in the Pedagogue catalogue, with the difficulty of their piano pieces.", DESCRIPTION_LIMIT),
        "canonical": url,
        "robots": "index, follow",
        "og_type": "website",
        "og_title": "Piano composers and their pieces",
        "image": None,
        "jsonld": [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "ItemList",
                        "name": "Piano composers",
                        "itemListElement": [{"@type": "ListItem", "position": index, "name": group["composer"].name, "url": site(f"/composers/{group['slug']}")} for index, group in enumerate(groups, start=1)],
                    },
                    breadcrumbs([("Composers", url)]),
                ],
            }
        ],
    }


def sitemap_xml(entries: dict, extra: list[str]) -> str:
    rows: list[tuple[str, Optional[str]]] = [(site(path), None) for path in extra]
    rows += [(site(f"/composers/{slug}"), None) for slug in entries["composers"]]
    for slug, changed in entries["pieces"]:
        rows.append((site(f"/music/{slug}"), changed.date().isoformat() if changed else None))
    body = []
    for location, modified in rows:
        line = f"<url><loc>{escape(location)}</loc>"
        if modified:
            line += f"<lastmod>{modified}</lastmod>"
        body.append(line + "</url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(body) + "\n</urlset>\n"


PRIVATE_PATHS = (
    "/api/",
    "/admin/",
    "/onboarding",
    "/repertoire",
    "/practice",
    "/progress",
    "/progression",
    "/performances",
    "/constellation",
    "/roulette",
    "/observatory",
    "/settings",
)


def robots_txt() -> str:
    if not settings.is_production:
        return "User-agent: *\nDisallow: /\n"
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {path}" for path in PRIVATE_PATHS]
    lines += ["", f"Sitemap: {site('/sitemap.xml')}", ""]
    return "\n".join(lines)
