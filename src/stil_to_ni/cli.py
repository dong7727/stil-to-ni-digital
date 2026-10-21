from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compiler import compile_pattern
from .converter import ConversionError, convert_file
from .profiles import PROFILES


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
    labels = parser.add_mutually_exclusive_group()
    labels.add_argument(
        "--no-labels",
        dest="keep_labels", action="store_false",
        help="omit STIL call labels from generated patterns",
    )
    labels.add_argument("--keep-labels", dest="keep_labels", action="store_true",
                        help="keep all labels; fail before writing if there are more than 8191")
    parser.set_defaults(keep_labels=None)
    parser.add_argument("--progress", action="store_true", help="show overall stage progress on stderr")
    parser.add_argument(
        "--compile",
        action="store_true",
        help="compile generated .digipatsrc files to .digipat with the NI compiler",
    )
    parser.add_argument(
        "--pins",
        action="append",
        metavar="PIN[,PIN...]",
        help="include only these pins; repeat the option or separate names with commas",
    )
    parser.add_argument("--compiler", type=Path, help="path to DigitalPatternCompiler.exe")
    parser.add_argument('--profile', choices=sorted(PROFILES), help='explicit hash-bound project profile')
    parser.add_argument('--fixed-policy', choices=['error', 'preserve_fixed_with_diagnostic'], default='error')
    parser.add_argument('--high-z-policy', choices=['error', 'midband'], default='error', help='midband maps compare-high-Z to M; requires station electrical validation')
    parser.add_argument('--time-scale', default='1', help='positive decimal scale for all timing fields')
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    def report_progress(percent: int, stage: str) -> None:
        if args.progress:
            print(f"{percent:3d}% {stage}", file=sys.stderr, flush=True)
    try:
        selected_pins = None
        if args.pins:
            selected_pins = [
                pin.strip()
                for group in args.pins
                for pin in group.split(",")
                if pin.strip()
            ]
        result = convert_file(
            args.input,
            args.output_dir,
            expand_scan=args.expand_scan,
            keep_labels=args.keep_labels,
            selected_pins=selected_pins,
            project_profile=args.profile,
            fixed_policy=args.fixed_policy,
            high_z_policy=args.high_z_policy,
            time_scale=args.time_scale,
            progress=lambda percent, stage: report_progress(
                percent * 70 // 100 if args.compile else percent, stage),
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
            for index, source in enumerate(sources):
                output = source.with_suffix(".digipat")
                completed = compile_pattern(
                    source,
                    result.files["pinmap"],
                    output,
                    compiler=args.compiler,
                    progress=lambda percent, stage: report_progress(
                        70 + (index * 100 + percent) * 30 // (len(sources) * 100),
                        f"{stage} [{index + 1}/{len(sources)}]"),
                )
                print(completed.stdout.strip())
                print(f"compiled_pattern: {output}")
    except (ConversionError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
