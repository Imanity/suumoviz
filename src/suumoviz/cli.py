"""Command line: ``suumoviz crawl | merge | daily | build | decode | encode``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from suumoviz import codec
from suumoviz.build import BuildError, build_site
from suumoviz.categories import CATEGORIES
from suumoviz.crawl import CrawlOptions, run_crawl
from suumoviz.fetch import Fetcher
from suumoviz.merge import MergeError, merge_day
from suumoviz.state import now_jst

MIN_INTERVAL = 5.0


def _categories(value: str) -> tuple[str, ...]:
    keys = tuple(k.strip() for k in value.split(",") if k.strip())
    unknown = set(keys) - set(CATEGORIES)
    if unknown or not keys:
        raise argparse.ArgumentTypeError(f"unknown categories: {sorted(unknown)}")
    return keys


def _interval(value: str) -> float:
    seconds = float(value)
    if seconds < MIN_INTERVAL:
        raise argparse.ArgumentTypeError(f"interval must be at least {MIN_INTERVAL} seconds")
    return seconds


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", type=date.fromisoformat, help="JST date (default: today)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--work-dir", type=Path, default=Path("work"))


def _crawl_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-pages", type=int, help="fetch at most N list pages")
    parser.add_argument("--categories", type=_categories, default=tuple(CATEGORIES))
    parser.add_argument("--interval", type=_interval, default=MIN_INTERVAL)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suumoviz")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="fetch today's rotation slot of list pages")
    _common(crawl)
    _crawl_args(crawl)
    crawl.add_argument("--dry-run", action="store_true", help="print the plan; fetch no list pages")
    crawl.add_argument(
        "--city-html", type=Path, help="read city_<category>.html from DIR instead of fetching"
    )

    merge = sub.add_parser("merge", help="merge work/{date}/ into the data tables")
    _common(merge)

    daily = sub.add_parser("daily", help="crawl, then merge the snapshot it wrote")
    _common(daily)
    _crawl_args(daily)

    build = sub.add_parser("build", help="write the web's area summary from the data tables")
    build.add_argument("--data-dir", type=Path, default=Path("data"))
    build.add_argument("--out", type=Path, default=Path("web/public/data"))

    decode = sub.add_parser("decode", help="print an obfuscated file in plain form")
    decode.add_argument("file", type=Path)

    encode = sub.add_parser(
        "encode", help="obfuscate files in place (directories: every *.csv below them)"
    )
    encode.add_argument("paths", type=Path, nargs="+")
    return parser


def _decode(path: Path) -> int:
    try:
        data = codec.read_bytes(path)
    except (OSError, codec.DecodeError) as exc:
        print(f"decode: {exc}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(data)
    sys.stdout.flush()
    return 0


def _encode(paths: list[Path]) -> int:
    files = [f for p in paths for f in (sorted(p.rglob("*.csv")) if p.is_dir() else [p])]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        print(f"encode: not found: {missing}", file=sys.stderr)
        return 1
    changed = sum(codec.encode_file(f) for f in files)
    print(f"encode: {changed} file(s) encoded, {len(files) - changed} already encoded")
    return 0


def _build(data_dir: Path, out: Path) -> int:
    try:
        result = build_site(data_dir, out)
    except BuildError as exc:
        print(f"build: {exc}", file=sys.stderr)
        return 1
    print("build: " + json.dumps(result.summary(), ensure_ascii=False))
    return 0


def _merge(day: date, data_dir: Path, work_dir: Path) -> int:
    snapshot = work_dir / day.isoformat()
    if not (snapshot / "run.json").exists():
        print(f"merge: no snapshot for {day} in {work_dir}; nothing to do")
        return 0
    try:
        result = merge_day(data_dir, snapshot)
    except MergeError as exc:
        print(f"merge: {exc}", file=sys.stderr)
        return 1
    print(
        "merge: "
        + json.dumps(
            {
                "date": result.day,
                "merged": result.merged,
                "quality": result.quality.summary(),
                **result.events,
            }
        )
    )
    return result.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "build":
        return _build(args.data_dir, args.out)
    if args.command == "decode":
        return _decode(args.file)
    if args.command == "encode":
        return _encode(args.paths)
    day = args.date or now_jst().date()

    if args.command == "merge":
        return _merge(day, args.data_dir, args.work_dir)

    dry_run = getattr(args, "dry_run", False)
    city_html = getattr(args, "city_html", None)
    options = CrawlOptions(
        day=day,
        data_dir=args.data_dir,
        work_dir=args.work_dir,
        dry_run=dry_run,
        max_pages=args.max_pages,
        city_html_dir=city_html,
        categories=args.categories,
    )
    offline = dry_run and city_html is not None
    fetcher = None if offline else Fetcher(interval=args.interval)
    crawl_code = run_crawl(options, fetcher).exit_code
    if args.command == "crawl":
        return crawl_code
    return max(crawl_code, _merge(day, args.data_dir, args.work_dir))


if __name__ == "__main__":
    raise SystemExit(main())
