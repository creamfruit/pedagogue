import argparse
import json
import sys
from pathlib import Path

from . import config, pipeline
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

    fetch = commands.add_parser("fetch", help="download the score files of the works that passed the earlier stages")
    fetch.add_argument("--limit", type=int)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    ws = Workspace(arguments.work)
    with PoliteClient(ws.root) as client:
        if arguments.command == "crawl":
            result = pipeline.crawl(ws, client, arguments.source or pipeline.SOURCES, max_pages=arguments.max_pages, limit=arguments.limit)
        else:
            result = pipeline.fetch(ws, client, pipeline.STAGE_CRAWL, limit=arguments.limit)
        result["requests"] = client.requests_made
        result["cache_hits"] = client.cache_hits
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
