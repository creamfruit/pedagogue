import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from . import config
from .licences import Licence, parse_licence
from .models import Candidate, Rejection
from .polite import PoliteClient

RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
ARCHIVE = "https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
MEMBER = re.compile(r"^[^/]+/scores/(?P<composer>[^/]+)/(?P<set>[^/]+)/(?P<song>[^/]+)/(?P<prefix>[a-z]+)(?P<id>\d+)\.mscx$")
NUMBER_PREFIX = re.compile(r"^(\d+[a-z]?)[_\-. ]+")
PIANO_WORDS = re.compile(r"piano|klavier|keyboard|pianoforte|clavier", re.I)


@dataclass(frozen=True)
class Corpus:
    id: str
    repo: str
    branch: str
    label: str
    url: str
    has_piano: bool
    reason: str = ""


CORPORA = (
    Corpus("openscore-lieder", "OpenScore/Lieder", "main", "OpenScore Lieder Corpus", "https://musescore.com/openscore-lieder-corpus", True),
    Corpus(
        "openscore-quartets",
        "OpenScore/StringQuartets",
        "main",
        "OpenScore String Quartets",
        "https://musescore.com/openscore-string-quartets",
        False,
        "the corpus is string quartets only, so it has no piano part",
    ),
)


def raw_url(corpus: Corpus, path: str) -> str:
    return RAW.format(repo=corpus.repo, branch=corpus.branch, path=path)


def corpus_licence(client: PoliteClient, corpus: Corpus) -> Optional[Licence]:
    reply = client.get(raw_url(corpus, "LICENSE.txt"), max_age=config.WIKIDATA_MAX_AGE_SECONDS)
    if not reply.ok:
        return None
    text = reply.text
    if re.search(r"CC0 1\.0 Universal", text):
        return parse_licence("CC0 1.0 Universal")
    return None


def load_yaml(client: PoliteClient, corpus: Corpus, name: str) -> dict:
    reply = client.get(raw_url(corpus, f"data/{name}"), max_age=config.CATALOGUE_MAX_AGE_SECONDS)
    if not reply.ok:
        return {}
    return yaml.safe_load(reply.text) or {}


def readable(name: str) -> str:
    return " ".join(name.replace("_", " ").split())


def song_title(directory: str) -> tuple[str, str]:
    prefix = ""
    found = NUMBER_PREFIX.match(directory)
    if found:
        prefix = found.group(1)
        directory = directory[found.end() :]
    return readable(directory), prefix


def has_piano(instruments: Optional[str]) -> bool:
    return True if not instruments else bool(PIANO_WORDS.search(instruments))


def candidates_from_archive(
    corpus: Corpus,
    licence: Licence,
    archive: Path,
    scores: dict,
    composers: dict,
    limit: Optional[int] = None,
) -> tuple[list[Candidate], list[Rejection]]:
    by_path = {str(entry.get("path")): (key, entry) for key, entry in scores.items() if isinstance(entry, dict)}
    people = {str(entry.get("path")): entry for entry in composers.values() if isinstance(entry, dict)}
    found: list[Candidate] = []
    rejected: list[Rejection] = []
    with zipfile.ZipFile(archive) as bundle:
        members = sorted(name for name in bundle.namelist() if MEMBER.match(name))
    for member in members:
        parts = MEMBER.match(member)
        composer_dir, set_dir, song_dir, score_id = parts.group("composer"), parts.group("set"), parts.group("song"), parts.group("id")
        path = f"{composer_dir}/{set_dir}/{song_dir}"
        meta_key, meta = by_path.get(path, (None, {}))
        person = people.get(composer_dir, {})
        title, prefix = song_title(song_dir)
        name = person.get("name") or readable(composer_dir.split(",_", 1)[-1] + " " + composer_dir.split(",_", 1)[0])
        instruments = meta.get("instruments")
        if not has_piano(instruments):
            rejected.append(Rejection(corpus.id, score_id, title, name, "instrument", f"no piano part ({instruments})"))
            continue
        qid = person.get("wikidata")
        found.append(
            Candidate(
                source=corpus.id,
                source_id=score_id,
                title=title,
                composer=name,
                source_url=f"https://musescore.com/score/{score_id}",
                licence=licence,
                licence_text="CC0 1.0 Universal",
                instrument=instruments or "Voice, Piano",
                born=int(person["born"]) if str(person.get("born", "")).isdigit() else None,
                died=int(person["died"]) if str(person.get("died", "")).isdigit() else None,
                composer_qid=str(qid) if qid else None,
                attribution=f"{corpus.label} ({corpus.url})",
                parent=readable(set_dir) if set_dir != "_" else "",
                files={"archive": str(archive), "member": member},
                extra={
                    "path": path,
                    "number": prefix,
                    "lyricist": meta.get("lyricist", ""),
                    "language": meta.get("language", ""),
                    "repository": f"https://github.com/{corpus.repo}/blob/{corpus.branch}/{member.split('/', 1)[1]}",
                    "composer_page": person.get("link", ""),
                },
            )
        )
        if limit is not None and len(found) >= limit:
            break
    return found, rejected


def crawl(client: PoliteClient, corpus: Corpus, work_dir: Path, limit: Optional[int] = None) -> tuple[list[Candidate], list[Rejection]]:
    licence = corpus_licence(client, corpus)
    if licence is None:
        return [], [Rejection(corpus.id, "*", corpus.label, "", "licence", "the repository licence could not be confirmed as CC0")]
    if not corpus.has_piano:
        return [], [Rejection(corpus.id, "*", corpus.label, "", "instrument", corpus.reason)]
    scores = load_yaml(client, corpus, "scores.yaml")
    composers = load_yaml(client, corpus, "composers.yaml")
    archive = client.download(ARCHIVE.format(repo=corpus.repo, branch=corpus.branch), work_dir / "archives" / f"{corpus.id}.zip")
    return candidates_from_archive(corpus, licence, archive, scores, composers, limit)


def extract_member(candidate: Candidate, work_dir: Path) -> Path:
    target = work_dir / "files" / candidate.source / f"{candidate.source_id}.mscx"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(candidate.files["archive"]) as bundle:
        target.write_bytes(bundle.read(candidate.files["member"]))
    return target
