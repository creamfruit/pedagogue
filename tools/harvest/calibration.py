import json
from pathlib import Path
from typing import Optional

from . import difficulty
from .naming import catalogue_number
from .workspace import Workspace


def load_features(ws: Workspace, candidate) -> dict:
    return json.loads(ws.abs(candidate.local["features"]).read_text(encoding="utf-8"))["features"]


def label_for(candidate) -> str:
    composer = (candidate.extra.get("composer_label") or candidate.composer).split()[-1]
    return f"{composer}: {candidate.title}"[:80]


def ladder_rows(ws: Workspace, source_stage: str) -> list:
    best: dict = {}
    for candidate in ws.read_stage(source_stage):
        composer = candidate.extra.get("composer_label") or candidate.composer
        entry = difficulty.ladder_entry(candidate.title, composer, catalogue_number(candidate.catalog_number))
        if entry is None:
            continue
        features = load_features(ws, candidate)
        busy = features["notes"]["nps_p90"]
        held = best.get(id(entry))
        if held is None or busy > held["busy"]:
            best[id(entry)] = {"entry": entry, "label": label_for(candidate), "ladder": float(entry.score), "features": features, "busy": busy}
    return list(best.values())


def calibrate(ws: Workspace, source_stage: str, *, model_path: Optional[Path] = None) -> dict:
    rows = ladder_rows(ws, source_stage)
    anchors = {id(entry) for _, _, _, entry in difficulty.anchor_entries() if entry is not None}
    training = [(difficulty.terms(row["features"]), row["ladder"], difficulty.ANCHOR_WEIGHT if id(row["entry"]) in anchors else 1.0) for row in rows]
    model = difficulty.fit(training)
    for row in rows:
        row["computed"] = model.score(row["features"])
    model.save(model_path or difficulty.MODEL_PATH)
    text = difficulty.report(rows, model)
    (ws.root / "calibration-report.md").write_text(text, encoding="utf-8")
    return {
        "pieces_compared": len(rows),
        "rmse": round(model.in_sample_rmse, 2),
        "leave_one_out_rmse": round(model.leave_one_out_rmse, 2),
        "report": str(ws.root / "calibration-report.md"),
        "text": text,
    }
