import hashlib
import json
import os
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from . import features as feature_module
from . import scoredata
from .models import Candidate, Rejection
from .workspace import Workspace

STAGE_EXTRACT = "04-extract"


def digest(paths: list) -> str:
    hasher = hashlib.sha256()
    for path in paths:
        hasher.update(Path(path).read_bytes())
    return hasher.hexdigest()


def source_files(ws: Workspace, candidate: Candidate) -> tuple[str, Path, list]:
    if "mid" in candidate.local:
        return "mid", ws.abs(candidate.local["mid"]), [ws.abs(candidate.local["ly"]), ws.abs(candidate.local["mid"])]
    return "mxl", ws.abs(candidate.local["mxl"]), [ws.abs(candidate.local["mxl"])]


def reference_for(data, measured: dict) -> dict:
    from app.services.reference_notes import build_payload

    notes = [(hit.onset, pitch, hit.bar) for hit in data.hits for pitch in hit.pitches]
    used = {bar for _, _, bar in notes}
    starts = {number: start for number, start, _ in data.bars if number in used}
    lengths = {number: length for number, _, length in data.bars if number in used}
    return build_payload(notes, starts, lengths, measured["tempo"]["mean_bpm"])


def analyse_job(job: dict) -> dict:
    warnings.filterwarnings("ignore")
    try:
        lilypond_text = Path(job["ly"]).read_text(encoding="utf-8", errors="replace") if job.get("ly") else None
        data = scoredata.load_score(Path(job["path"]), job["kind"], lilypond_text)
        measured = feature_module.extract(data)
        return {"key": job["key"], "features": measured, "vector": feature_module.to_vector(measured), "reference": reference_for(data, measured)}
    except (scoredata.UnreadableScore, ValueError) as error:
        return {"key": job["key"], "error": str(error)}
    except Exception as error:
        return {"key": job["key"], "error": f"{type(error).__name__}: {error}"}


def output_path(ws: Workspace, candidate: Candidate) -> Path:
    return ws.root / "features" / candidate.source / f"{candidate.source_id}.json"


def extract(ws: Workspace, source_stage: str, *, workers: Optional[int] = None, limit: Optional[int] = None, say=print) -> dict:
    candidates = ws.read_stage(source_stage)
    if limit is not None:
        candidates = candidates[:limit]
    jobs, by_key = [], {}
    kept: list[Candidate] = []
    rejected: list[Rejection] = []
    for candidate in candidates:
        by_key[candidate.key] = candidate
        target = output_path(ws, candidate)
        kind, path, hashed = source_files(ws, candidate)
        candidate.extra["content_hash"] = digest(hashed)
        held = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        if held.get("content_hash") == candidate.extra["content_hash"] and "reference" in held:
            candidate.local["features"] = ws.rel(target)
            kept.append(candidate)
            continue
        jobs.append({"key": candidate.key, "path": str(path), "kind": kind, "ly": str(ws.abs(candidate.local["ly"])) if "ly" in candidate.local else None})
    done = 0
    with ProcessPoolExecutor(max_workers=workers or max((os.cpu_count() or 2) - 1, 1)) as pool:
        futures = [pool.submit(analyse_job, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            candidate = by_key[result["key"]]
            done += 1
            if "error" in result:
                rejected.append(Rejection(candidate.source, candidate.source_id, candidate.title, candidate.composer, "extract", result["error"]))
            else:
                target = output_path(ws, candidate)
                target.parent.mkdir(parents=True, exist_ok=True)
                payload = {"content_hash": candidate.extra["content_hash"], "features": result["features"], "vector": result["vector"], "reference": result["reference"]}
                target.write_text(json.dumps(payload), encoding="utf-8")
                candidate.local["features"] = ws.rel(target)
                kept.append(candidate)
            if done % 50 == 0:
                say(f"extract: {done}/{len(jobs)} scores measured")
    kept.sort(key=lambda candidate: (candidate.source, int(candidate.source_id)))
    count, dropped = ws.write_stage(STAGE_EXTRACT, kept, rejected)
    return {"kept": count, "rejected": dropped, "measured_now": len(jobs)}
