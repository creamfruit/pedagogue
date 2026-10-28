import json
import os
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from . import passages as passage_module
from . import render, scoredata
from .models import Candidate
from .workspace import Workspace

STAGE_RENDER = "05-render"


def image_folder(ws: Workspace, candidate: Candidate) -> Path:
    return ws.root / "images" / candidate.source / candidate.source_id


def render_one(job: dict) -> dict:
    warnings.filterwarnings("ignore")
    folder = Path(job["folder"])
    folder.mkdir(parents=True, exist_ok=True)
    features = job["features"]
    found = passage_module.detect(features)
    data = None
    for item in found:
        name = f"{item['start']}-{item['end']}.svg"
        target = folder / name
        item["image"], item["method"] = None, None
        if target.exists():
            item["image"], item["method"] = name, "cached"
            continue
        svg, method = None, None
        try:
            if job["ly"]:
                svg, method = render.render_lilypond(Path(job["ly"]), item["start"], item["end"], Path(job["ly"]).parent), "lilypond"
            elif job["mxl"]:
                svg, method = render.render_musicxml(Path(job["mxl"]), features["per_bar"]["numbers"], item["start"], item["end"]), "musicxml"
            if svg is None and job["mid"]:
                if data is None:
                    text = Path(job["ly"]).read_text(encoding="utf-8", errors="replace") if job["ly"] else None
                    data = scoredata.load_score(Path(job["mid"]), "mid", text)
                svg, method = render.render_from_notes(data, item["start"], item["end"]), "notes"
        except render.RenderUnavailable:
            raise
        except Exception:
            svg = None
        if svg:
            target.write_text(svg, encoding="utf-8")
            item["image"], item["method"] = name, method
    techniques = passage_module.piece_techniques(passage_module.bar_signals(features["per_bar"]), features["length"]["minutes"])
    index = {"passages": found, "techniques": techniques, "hardest_bars": passage_module.hardest_bars(features)}
    (folder / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return {"key": job["key"], "images": sum(1 for item in found if item["image"]), "passages": len(found)}


def render_stage(ws: Workspace, source_stage: str, *, workers: Optional[int] = None, limit: Optional[int] = None, say=print) -> dict:
    candidates = ws.read_stage(source_stage)
    if limit is not None:
        candidates = candidates[:limit]
    jobs = []
    for candidate in candidates:
        payload = json.loads(ws.abs(candidate.local["features"]).read_text(encoding="utf-8"))
        jobs.append(
            {
                "key": candidate.key,
                "folder": str(image_folder(ws, candidate)),
                "features": payload["features"],
                "ly": str(ws.abs(candidate.local["ly"])) if "ly" in candidate.local else None,
                "mid": str(ws.abs(candidate.local["mid"])) if "mid" in candidate.local else None,
                "mxl": str(ws.abs(candidate.local["mxl"])) if "mxl" in candidate.local else None,
            }
        )
    by_key = {candidate.key: candidate for candidate in candidates}
    totals = {"passages": 0, "images": 0}
    done = 0
    with ProcessPoolExecutor(max_workers=workers or max((os.cpu_count() or 2) - 1, 1)) as pool:
        for future in as_completed([pool.submit(render_one, job) for job in jobs]):
            result = future.result()
            totals["passages"] += result["passages"]
            totals["images"] += result["images"]
            candidate = by_key[result["key"]]
            candidate.local["passages"] = (image_folder(ws, candidate) / "index.json").relative_to(ws.root).as_posix()
            done += 1
            if done % 25 == 0:
                say(f"render: {done}/{len(jobs)} pieces, {totals['images']} images")
    ordered = sorted(candidates, key=lambda candidate: (candidate.source, int(candidate.source_id)))
    count, _ = ws.write_stage(STAGE_RENDER, ordered, [])
    return {"pieces": count, **totals}
