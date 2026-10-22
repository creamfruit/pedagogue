import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Optional

from datetime import date

from . import mutopia, musescore, openscore
from .composers import ComposerGate
from .models import Candidate, Rejection
from .polite import FetchError, PoliteClient
from .workspace import Workspace

STAGE_CRAWL = "01-crawl"
STAGE_COMPOSERS = "02-composers"
STAGE_FETCH = "03-fetch"

SOURCES = ("mutopia", "openscore")


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def crawl_mutopia(client: PoliteClient, max_pages: Optional[int], limit: Optional[int]) -> tuple[list[Candidate], list[Rejection]]:
    found: list[Candidate] = []
    rejected: list[Rejection] = []
    seen = 0
    for entry in mutopia.crawl(client, max_pages=max_pages):
        seen += 1
        candidate, rejection = mutopia.candidate_from(entry)
        if candidate is not None:
            found.append(candidate)
        if rejection is not None:
            rejected.append(rejection)
        if seen % 100 == 0:
            say(f"mutopia: {seen} catalogue entries read, {len(found)} kept")
        if limit is not None and len(found) >= limit:
            break
    return found, rejected


def crawl(
    ws: Workspace,
    client: PoliteClient,
    sources: Iterable[str] = SOURCES,
    *,
    max_pages: Optional[int] = None,
    limit: Optional[int] = None,
) -> dict:
    found: list[Candidate] = []
    rejected: list[Rejection] = []
    for source in sources:
        if source == "mutopia":
            more, fewer = crawl_mutopia(client, max_pages, limit)
            found += more
            rejected += fewer
        elif source == "openscore":
            for corpus in openscore.CORPORA:
                more, fewer = openscore.crawl(client, corpus, ws.root, limit)
                found += more
                rejected += fewer
    kept, dropped = ws.write_stage(STAGE_CRAWL, found, rejected)
    return {"kept": kept, "rejected": dropped, "by_source": dict(Counter(item.source for item in found))}


def filter_composers(ws: Workspace, client: PoliteClient, source_stage: str = STAGE_CRAWL, *, today: Optional[date] = None) -> dict:
    gate = ComposerGate(client, today=today)
    kept: list[Candidate] = []
    rejected: list[Rejection] = []
    for candidate in ws.read_stage(source_stage):
        verdict = gate.check(candidate.composer, candidate.born, candidate.died, candidate.composer_qid)
        if verdict.accepted:
            candidate.composer_qid = verdict.qid
            candidate.composer_died_on = verdict.died_on
            candidate.extra["composer_label"] = verdict.label
            candidate.extra["composer_check"] = verdict.reason
            kept.append(candidate)
        else:
            rejected.append(Rejection(candidate.source, candidate.source_id, candidate.title, candidate.composer, "composer", verdict.reason))
    count, dropped = ws.write_stage(STAGE_COMPOSERS, kept, rejected)
    return {"kept": count, "rejected": dropped, "composers_checked": gate.checked}


def fetch_mutopia(ws: Workspace, client: PoliteClient, candidate: Candidate) -> Optional[str]:
    folder = ws.files / "mutopia" / candidate.source_id
    local, problem, header = mutopia.fetch_files(client, candidate, folder)
    if problem:
        return problem
    mutopia.apply_header(candidate, header)
    candidate.local = {kind: ws.rel(Path(path)) for kind, path in local.items()}
    return None


def fetch_openscore(ws: Workspace, candidates: list[Candidate]) -> dict[str, Optional[str]]:
    pairs = []
    for candidate in candidates:
        source = openscore.extract_member(candidate, ws.root)
        pairs.append((candidate, source, source.with_suffix(".mxl")))
    try:
        musescore.convert_batch((source, target) for _, source, target in pairs)
    except musescore.ConversionUnavailable as error:
        return {candidate.key: str(error) for candidate, _, _ in pairs}
    outcome: dict[str, Optional[str]] = {}
    for candidate, _, target in pairs:
        if target.exists():
            candidate.local = {"mxl": ws.rel(target)}
            outcome[candidate.key] = None
        else:
            outcome[candidate.key] = "MuseScore could not convert the score to MusicXML"
    return outcome


def fetch(ws: Workspace, client: PoliteClient, source_stage: str, *, limit: Optional[int] = None) -> dict:
    candidates = ws.read_stage(source_stage)
    if limit is not None:
        candidates = candidates[:limit]
    kept: list[Candidate] = []
    rejected: list[Rejection] = []
    scores = [candidate for candidate in candidates if candidate.source.startswith("openscore")]
    for index, candidate in enumerate(candidates, start=1):
        if candidate.source != "mutopia":
            continue
        try:
            problem = fetch_mutopia(ws, client, candidate)
        except (FetchError, OSError, ValueError) as error:
            problem = f"could not fetch the files: {error}"
        if problem:
            rejected.append(Rejection(candidate.source, candidate.source_id, candidate.title, candidate.composer, "fetch", problem))
        else:
            kept.append(candidate)
        if index % 25 == 0:
            say(f"fetch: {index}/{len(candidates)} processed, {len(kept)} kept")
    if scores:
        outcome = fetch_openscore(ws, scores)
        for candidate in scores:
            problem = outcome.get(candidate.key)
            if problem:
                rejected.append(Rejection(candidate.source, candidate.source_id, candidate.title, candidate.composer, "fetch", problem))
            else:
                kept.append(candidate)
    count, dropped = ws.write_stage(STAGE_FETCH, kept, rejected)
    return {"kept": count, "rejected": dropped}


def reasons(ws: Workspace, stages: Iterable[str]) -> Counter:
    tally: Counter = Counter()
    for stage in stages:
        for row in ws.rejections(stage):
            tally[(row["stage"], row["reason"].split("(")[0].strip())] += 1
    return tally
