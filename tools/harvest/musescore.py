import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from . import config

CHUNK = 40
TIMEOUT_SECONDS = 900


class ConversionUnavailable(Exception):
    pass


def available(binary: Optional[str] = None) -> bool:
    return Path(binary or config.MUSESCORE_BIN).exists()


def convert_batch(pairs: Iterable[tuple[Path, Path]], binary: Optional[str] = None) -> list[Path]:
    binary = binary or config.MUSESCORE_BIN
    if not available(binary):
        raise ConversionUnavailable(f"MuseScore was not found at {binary}; set MUSESCORE_BIN to convert OpenScore files")
    todo = [(source, target) for source, target in pairs if not target.exists()]
    for start in range(0, len(todo), CHUNK):
        chunk = todo[start : start + CHUNK]
        for _, target in chunk:
            target.parent.mkdir(parents=True, exist_ok=True)
        job = [{"in": str(source), "out": str(target)} for source, target in chunk]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(job, handle)
            job_path = handle.name
        try:
            subprocess.run([binary, "-j", job_path], capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        finally:
            os.unlink(job_path)
    return [target for _, target in todo if target.exists()]
