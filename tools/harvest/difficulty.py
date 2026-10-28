import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from . import config

MODEL_PATH = Path(__file__).resolve().parent / "difficulty_model.json"
MODEL_VERSION = "harvest-difficulty-1"
LAMBDAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
ANCHOR_WEIGHT = 40.0
FLOOR, CEILING = 1.0, 99.0

ANCHORS = (
    ("Für Elise", "Beethoven", 30.0),
    ("Ballade No. 1", "Chopin", 70.0),
    ("La Campanella", "Liszt", 90.0),
    ("Islamey", "Balakirev", 98.0),
)


def soft_log(value: float) -> float:
    return math.log1p(max(value, 0.0))


def terms(features: dict) -> dict:
    notes, span, leaps, octaves = features["notes"], features["span"], features["leaps"], features["octaves"]
    tuplets, runs = features["tuplets"], features["runs"]
    bars = max(features["bars"], 1)
    return {
        "speed_p90": soft_log(notes["nps_p90"]),
        "speed_peak": soft_log(notes["nps_peak"]),
        "density_p90": soft_log(notes["p90_per_bar"]),
        "reach_max": span["max"] / 24.0,
        "reach_window": span["window_p95"] / 36.0,
        "leap_size": leaps["top5_mean"] / 48.0,
        "leap_rate": min(leaps["ge_octave"] / bars, 4.0) / 4.0,
        "octave_runs": min(octaves["repeated"] / bars / 8.0, 1.0),
        "octave_share": octaves["fraction"],
        "fast_runs": runs["fraction"],
        "tuplets": tuplets["fraction"] + tuplets["complex_fraction"],
        "length": soft_log(features["length"]["minutes"]),
        "changes": soft_log(features["metre"]["changes"] + features["key"]["changes"] + features["tempo"]["changes"]),
        "polyphony": notes["polyphony_mean"] / 6.0,
    }


TERM_NAMES = tuple(terms({
    "notes": {"nps_p90": 0, "nps_peak": 0, "p90_per_bar": 0, "polyphony_mean": 0},
    "span": {"max": 0, "window_p95": 0},
    "leaps": {"top5_mean": 0, "ge_octave": 0},
    "octaves": {"repeated": 0, "fraction": 0},
    "tuplets": {"fraction": 0, "complex_fraction": 0},
    "runs": {"fraction": 0},
    "length": {"minutes": 0},
    "metre": {"changes": 0},
    "key": {"changes": 0},
    "tempo": {"changes": 0},
    "bars": 1,
}))


@dataclass
class Model:
    version: str
    names: list
    means: list
    scales: list
    coefficients: list
    intercept: float
    ridge: float
    fitted_on: int = 0
    in_sample_rmse: float = 0.0
    leave_one_out_rmse: float = 0.0
    dropped: list = field(default_factory=list)

    def raw(self, features: dict) -> float:
        values = terms(features)
        total = self.intercept
        for name, mean, scale, weight in zip(self.names, self.means, self.scales, self.coefficients):
            total += weight * (values[name] - mean) / scale
        return total

    def score(self, features: dict) -> float:
        return round(float(min(max(self.raw(features), FLOOR), CEILING)), 1)

    def to_json(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_json(cls, data: dict) -> "Model":
        return cls(**data)

    def save(self, path: Path = MODEL_PATH) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> Optional["Model"]:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None


def design(rows: list) -> tuple:
    matrix = np.array([[row[0][name] for name in TERM_NAMES] for row in rows], dtype=float)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales < 1e-9] = 1.0
    return (matrix - means) / scales, means, scales


def solve(standard: np.ndarray, targets: np.ndarray, weights: np.ndarray, ridge: float) -> tuple:
    active = list(range(standard.shape[1]))
    while True:
        x = np.hstack([np.ones((standard.shape[0], 1)), standard[:, active]])
        penalty = np.diag([0.0] + [ridge] * len(active))
        w = np.diag(weights)
        beta = np.linalg.solve(x.T @ w @ x + penalty, x.T @ w @ targets)
        negative = [(beta[index + 1], active[index]) for index in range(len(active)) if beta[index + 1] < 0]
        if not negative:
            break
        active.remove(min(negative)[1])
    coefficients = np.zeros(standard.shape[1])
    for index, column in enumerate(active):
        coefficients[column] = beta[index + 1]
    return float(beta[0]), coefficients


def predict_standard(standard: np.ndarray, intercept: float, coefficients: np.ndarray) -> np.ndarray:
    return np.clip(intercept + standard @ coefficients, FLOOR, CEILING)


def fit(rows: list, ridge: Optional[float] = None) -> Model:
    if len(rows) < 8:
        raise ValueError("too few ladder pieces to calibrate against")
    standard, means, scales = design(rows)
    targets = np.array([row[1] for row in rows], dtype=float)
    weights = np.array([row[2] for row in rows], dtype=float)

    def leave_one_out(value: float) -> float:
        errors = []
        for held in range(len(rows)):
            keep = np.arange(len(rows)) != held
            intercept, coefficients = solve(standard[keep], targets[keep], weights[keep], value)
            errors.append(predict_standard(standard[held : held + 1], intercept, coefficients)[0] - targets[held])
        return float(np.sqrt(np.mean(np.square(errors))))

    scored = {value: leave_one_out(value) for value in ([ridge] if ridge else LAMBDAS)}
    chosen = min(scored, key=scored.get)
    intercept, coefficients = solve(standard, targets, weights, chosen)
    fitted = predict_standard(standard, intercept, coefficients)
    return Model(
        version=MODEL_VERSION,
        names=list(TERM_NAMES),
        means=[float(value) for value in means],
        scales=[float(value) for value in scales],
        coefficients=[float(value) for value in coefficients],
        intercept=intercept,
        ridge=float(chosen),
        fitted_on=len(rows),
        in_sample_rmse=float(np.sqrt(np.mean(np.square(fitted - targets)))),
        leave_one_out_rmse=scored[chosen],
        dropped=[name for name, weight in zip(TERM_NAMES, coefficients) if weight == 0.0],
    )


def spearman(a: list, b: list) -> float:
    if len(a) < 3:
        return float("nan")
    rank_a = np.argsort(np.argsort(a)).astype(float)
    rank_b = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(rank_a, rank_b)[0, 1])


def ladder_entry(title: str, composer: str, catalogue: Optional[str] = None):
    from app.services.repertoire_reference import lookup

    return lookup(title, composer, catalogue)


def anchor_entries() -> list:
    found = []
    for name, composer, expected in ANCHORS:
        entry = ladder_entry(name, composer)
        found.append((name, composer, expected, entry))
    return found


def report(rows: list, model: Model) -> str:
    lines = ["# Difficulty calibration", "", f"Model `{model.version}`, fitted on {model.fitted_on} harvested pieces that are also on the reference ladder.", ""]
    lines.append("| Piece | Ladder | Computed | Error |")
    lines.append("|---|---:|---:|---:|")
    errors, ladder, computed = [], [], []
    for row in sorted(rows, key=lambda item: item["ladder"]):
        value = row["computed"]
        errors.append(value - row["ladder"])
        ladder.append(row["ladder"])
        computed.append(value)
        lines.append(f"| {row['label']} | {row['ladder']:.1f} | {value:.1f} | {value - row['ladder']:+.1f} |")
    squared = float(np.sqrt(np.mean(np.square(errors)))) if errors else float("nan")
    lines += [
        "",
        f"- Pieces compared: {len(rows)}",
        f"- RMSE in sample: {squared:.1f}; leave-one-out RMSE: {model.leave_one_out_rmse:.1f}",
        f"- Mean absolute error: {float(np.mean(np.abs(errors))):.1f}; bias: {float(np.mean(errors)):+.1f}",
        f"- Rank correlation with the ladder (Spearman): {spearman(ladder, computed):.2f}",
        f"- Terms the fit dropped: {', '.join(model.dropped) or 'none'}",
        "",
        "## Anchors",
        "",
        "| Anchor | Target | Ladder | Computed | In the harvested corpus |",
        "|---|---:|---:|---:|---|",
    ]
    by_entry = {id(row["entry"]): row for row in rows}
    for name, composer, expected, entry in anchor_entries():
        row = by_entry.get(id(entry)) if entry is not None else None
        ladder_value = f"{float(entry.score):.1f}" if entry is not None else "not on the ladder"
        if row is None:
            lines.append(f"| {name} ({composer}) | {expected:.0f} | {ladder_value} | n/a | no |")
        else:
            lines.append(f"| {name} ({composer}) | {expected:.0f} | {ladder_value} | {row['computed']:.1f} | yes: {row['label']} |")
    return "\n".join(lines) + "\n"
