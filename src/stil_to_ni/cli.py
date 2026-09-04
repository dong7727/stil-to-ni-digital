from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compiler import compile_pattern
from .converter import ConversionError, convert_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stil-to-ni",
        description="Convert a supported TetraMAX STIL scan pattern to NI-Digital files.",
    )
    parser.add_argument("input", type=Path, help="input .stil or .stil.gz file")
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument(
        "--expand-scan",
        action="store_true",
        help="also emit one ordinary NI vector line per test cycle (can be very large)",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="omit STIL call labels from generated patterns",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="compile generated .digipatsrc files to .digipat with the NI compiler",
    )
    parser.add_argument("--compiler", type=Path, help="path to DigitalPatternCompiler.exe")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        result = convert_file(
            args.input,
            args.output_dir,
            expand_scan=args.expand_scan,
            keep_labels=not args.no_labels,
        )
        print(f"Converted: {args.input}")
        print(f"Pins: {', '.join(result.pins)}")
        print(f"Test cycles: {result.cycles}")
        for kind, path in result.files.items():
            print(f"{kind}: {path}")

        if args.compile:
            sources = [result.files["pattern_source"]]
            if "expanded_pattern_source" in result.files:
                sources.append(result.files["expanded_pattern_source"])
            for source in sources:
                output = source.with_suffix(".digipat")
                completed = compile_pattern(
                    source,
                    result.files["pinmap"],
                    output,
                    compiler=args.compiler,
                )
                print(completed.stdout.strip())
                print(f"compiled_pattern: {output}")
    except (ConversionError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
