import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import calibration, config, extract, ingest, pipeline
from .polite import PoliteClient
from .workspace import Workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.harvest", description="Harvest open piano scores for Pedagogue")
    parser.add_argument("--work", type=Path, default=config.DEFAULT_WORK_DIR, help="folder for the cache, downloads and stage files")
    commands = parser.add_subparsers(dest="command", required=True)

    crawl = commands.add_parser("crawl", help="list the catalogues and keep works with a clear open licence")
    crawl.add_argument("--source", action="append", choices=pipeline.SOURCES, help="limit to one source; repeat for more")
    crawl.add_argument("--max-pages", type=int, help="stop the Mutopia crawl after this many listing pages")
    crawl.add_argument("--limit", type=int, help="keep at most this many works per source")

    commands.add_parser("composers", help="keep only works by composers who died more than seventy years ago, as recorded on Wikidata")

    fetch = commands.add_parser("fetch", help="download the score files of the works that passed the earlier stages")
    fetch.add_argument("--limit", type=int)

    measure = commands.add_parser("extract", help="measure each score with music21 and store its features and feature vector")
    measure.add_argument("--limit", type=int)
    measure.add_argument("--workers", type=int)

    commands.add_parser("calibrate", help="fit the difficulty score to the reference ladder and print the calibration report")

    load = commands.add_parser("ingest", help="write the measured works to the database; safe to run again")
    load.add_argument("--limit", type=int)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    ws = Workspace(arguments.work)
    with PoliteClient(ws.root) as client:
        if arguments.command == "crawl":
            result = pipeline.crawl(ws, client, arguments.source or pipeline.SOURCES, max_pages=arguments.max_pages, limit=arguments.limit)
        elif arguments.command == "composers":
            result = pipeline.filter_composers(ws, client)
        elif arguments.command == "fetch":
            result = pipeline.fetch(ws, client, pipeline.STAGE_COMPOSERS, limit=arguments.limit)
        elif arguments.command == "extract":
            result = extract.extract(ws, pipeline.STAGE_FETCH, workers=arguments.workers, limit=arguments.limit, say=pipeline.say)
        elif arguments.command == "calibrate":
            result = calibration.calibrate(ws, extract.STAGE_EXTRACT)
        else:
            result = asyncio.run(ingest.ingest(ws, extract.STAGE_EXTRACT, say=pipeline.say, limit=arguments.limit))
        result["requests"] = client.requests_made
        result["cache_hits"] = client.cache_hits
    text = result.pop("text", None)
    print(json.dumps(result, indent=2))
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
