from pathlib import Path
from typing import Iterable, Iterator

from .models import Candidate, Rejection, read_jsonl, write_jsonl


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state = self.root / "state"
        self.files = self.root / "files"
        self.state.mkdir(parents=True, exist_ok=True)
        self.files.mkdir(parents=True, exist_ok=True)

    def rel(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()

    def abs(self, relative: str) -> Path:
        return self.root / relative

    def stage_file(self, stage: str) -> Path:
        return self.state / f"{stage}.jsonl"

    def rejection_file(self, stage: str) -> Path:
        return self.state / f"{stage}.rejected.jsonl"

    def write_stage(self, stage: str, candidates: Iterable[Candidate], rejections: Iterable[Rejection]) -> tuple[int, int]:
        kept = write_jsonl(self.stage_file(stage), (candidate.to_json() for candidate in candidates))
        dropped = write_jsonl(self.rejection_file(stage), (rejection.to_json() for rejection in rejections))
        return kept, dropped

    def read_stage(self, stage: str) -> list[Candidate]:
        return [Candidate.from_json(row) for row in read_jsonl(self.stage_file(stage))]

    def rejections(self, stage: str) -> Iterator[dict]:
        return read_jsonl(self.rejection_file(stage))

    def has_stage(self, stage: str) -> bool:
        return self.stage_file(stage).exists()
