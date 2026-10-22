import re
from dataclasses import dataclass
from typing import Optional

PUBLIC_DOMAIN = "public-domain"
CC0 = "cc0"
CC_BY = "cc-by"

ALLOWED = (PUBLIC_DOMAIN, CC0, CC_BY)

PUBLIC_DOMAIN_URL = "https://creativecommons.org/publicdomain/mark/1.0/"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

RESTRICTIONS = re.compile(
    r"(?<![a-z])(sharealike|share[\s-]+alike|non[\s-]?commercial|noderiv\w*|no[\s-]+deriv\w*|nc|nd|sa)(?![a-z])"
)
VERSION = re.compile(r"(?<!\d)([1-4]\.\d)(?!\d)")


@dataclass(frozen=True)
class Licence:
    code: str
    name: str
    url: str
    version: Optional[str] = None


def normalise(text: str) -> str:
    cleaned = (text or "").lower().replace("_", " ")
    cleaned = re.sub(r"[()\[\]\"',;:]", " ", cleaned)
    return " ".join(cleaned.split())


def parse_licence(text: Optional[str]) -> Optional[Licence]:
    cleaned = normalise(text or "")
    if not cleaned:
        return None
    if cleaned in {"public domain", "public-domain", "publicdomain", "pd", "public domain mark", "public domain mark 1.0"}:
        return Licence(PUBLIC_DOMAIN, "Public Domain", PUBLIC_DOMAIN_URL)
    if re.fullmatch(r"cc0( 1\.0)?( universal)?|creative commons zero( 1\.0)?( universal)?|cc 0|cc zero", cleaned):
        return Licence(CC0, "CC0 1.0", CC0_URL, "1.0")
    if "cc0" in cleaned.split() or "creative commons zero" in cleaned:
        return Licence(CC0, "CC0 1.0", CC0_URL, "1.0")
    named = re.match(r"^(?:creative commons attribution|cc[\s-]?by)\b(.*)$", cleaned)
    if named:
        rest = named.group(1).strip()
        if RESTRICTIONS.search(rest) or re.search(r"[a-z]", re.sub(r"\b(international|generic|unported|license|licence|licensed|version|v)\b", "", rest)):
            return None
        version = VERSION.search(rest)
        if version is None:
            return None
        number = version.group(1)
        return Licence(CC_BY, f"CC BY {number}", f"https://creativecommons.org/licenses/by/{number}/", number)
    return None


def is_allowed(licence: Optional[Licence]) -> bool:
    return licence is not None and licence.code in ALLOWED


def rejection_reason(text: Optional[str]) -> str:
    cleaned = normalise(text or "")
    if not cleaned:
        return "no clear licence (none given)"
    if re.search(r"sharealike|share[\s-]+alike|(?<![a-z])sa(?![a-z])", cleaned):
        return f"licence not allowed (share-alike: {text})"
    if re.search(r"non[\s-]?commercial|(?<![a-z])nc(?![a-z])", cleaned):
        return f"licence not allowed (non-commercial: {text})"
    if re.search(r"noderiv|no[\s-]+deriv|(?<![a-z])nd(?![a-z])", cleaned):
        return f"licence not allowed (no derivatives: {text})"
    return f"no clear licence ({text})"
