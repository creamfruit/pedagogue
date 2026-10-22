import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .licences import Licence


@dataclass
class Candidate:
    source: str
    source_id: str
    title: str
    composer: str
    source_url: str
    licence: Licence
    licence_text: str
    instrument: str = ""
    born: Optional[int] = None
    died: Optional[int] = None
    composer_qid: Optional[str] = None
    composer_died_on: Optional[str] = None
    attribution: str = ""
    catalog_number: str = ""
    year: str = ""
    style: str = ""
    parent: str = ""
    files: dict = field(default_factory=dict)
    local: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "Candidate":
        values = dict(data)
        values["licence"] = Licence(**values["licence"])
        return cls(**values)


@dataclass
class Rejection:
    source: str
    source_id: str
    title: str
    composer: str
    stage: str
    reason: str

    def to_json(self) -> dict:
        return asdict(self)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    temporary.replace(path)
    return count


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
