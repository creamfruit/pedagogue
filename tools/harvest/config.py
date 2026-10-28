import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

CONTACT = os.environ.get("HARVEST_CONTACT", "https://github.com/creamfruit/pedagogue")
USER_AGENT = f"PedagogueHarvester/1.0 ({CONTACT})"

DEFAULT_WORK_DIR = Path(os.environ.get("HARVEST_DIR") or Path.home() / ".cache" / "pedagogue-harvest")

MIN_INTERVAL_SECONDS = {
    "www.mutopiaproject.org": 1.5,
    "www.wikidata.org": 1.0,
    "query.wikidata.org": 2.0,
    "raw.githubusercontent.com": 1.0,
    "codeload.github.com": 2.0,
    "api.github.com": 1.5,
}
DEFAULT_MIN_INTERVAL = 1.5

CATALOGUE_MAX_AGE_SECONDS = 7 * 24 * 3600
WIKIDATA_MAX_AGE_SECONDS = 30 * 24 * 3600

MIN_AGE_YEARS = 70

MUSESCORE_BIN = os.environ.get("MUSESCORE_BIN", r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe")
LILYPOND_BIN = os.environ.get("LILYPOND_BIN", "lilypond")
