# stil-to-ni-digital

`stil-to-ni-digital` converts a practical scan-oriented subset of STIL into files
used by NI Digital Pattern Editor and NI PXI Digital Pattern Instruments:

- human-readable pattern source (`.digipatsrc`)
- timing sheet (`.digitiming`)
- logical pin map (`.pinmap`)
- optionally, compiled pattern (`.digipat`) when NI's compiler is installed

NI documents `.digipatsrc` as the human-readable form used for programmatic
pattern generation and migration, while `.digipat` is the compiled pattern used
by NI-Digital. See [NI's migration overview](https://www.ni.com/en/shop/electronic-test-instrumentation/digital-instruments/what-are-digital-pattern-instruments/important-considerations-when-migrating-to-the-digital-pattern-i.html).

> [!IMPORTANT]
> This project is **not a complete IEEE 1450 parser**. Version 0.4 targets the
> common flat, scan-oriented STIL subset emitted by Synopsys TetraMAX. It fails
> on unsupported constructs rather than silently changing pattern semantics.

## Features

- Parses signals, ordered signal groups, waveform tables, multiple scan chains,
  procedures, macros, calls, conditions, vectors, and shift blocks.
- Supports unequal parallel scan-chain lengths with semantics-preserving padding.
- Resolves waveform events per pin and WFT; compare-high-Z requires an explicit
  `--high-z-policy midband` to generate NI `M` (electrical equivalence unverified).
- Preserves procedure-local Fixed constraints; conflicting assignments fail by
  default or are recorded under an explicitly selected preservation policy.
- Inspects the STIL first and lets desktop users select the output pins.
- Converts STIL `P` waveforms into dedicated NI timesets using
  `ReturnToLow`/`ReturnToHigh` edges.
- Keeps long scan data compact with NI `scan()` blocks.
- Automatically omits location labels above NI's 8191-label limit, while
  retaining every location in `pattern_labels.csv` (zero-based execution cycle).
- Shows stage-weighted percentage progress in the GUI or with `--progress`.
  NI compile/decompile stages hold their percentage while the external tool runs.
- `--expand-scan` emits one ordinary NI vector statement per test cycle.
- Verifies the generated cycle count against the TetraMAX summary when present.
- Provides a Windows desktop app with file selection, drag-and-drop, progress,
  and conversion logs.
- The command-line converter uses only the Python standard library.
- Can invoke `DigitalPatternCompiler.exe` and produce `.digipat` files.
- Automatically decompiles compiled patterns and checks full source round-trip.
- Records input/config/output hashes, macro timelines and stage validation in a manifest.

## Windows desktop app

Download `STIL-to-NI-Digital.exe` from the
[latest release](https://github.com/dong7727/stil-to-ni-digital/releases/latest).
No Python installation is required.

For installation, GUI options, output-file explanations, NI workflow,
troubleshooting, and production validation, see the
[detailed Chinese user guide](docs/USER_GUIDE_ZH-CN.md).

1. Double-click `STIL-to-NI-Digital.exe`.
2. Drag a `.stil` or `.stil.gz` file into the window, or click **Browse**.
3. Wait for the pin and scan-chain inspection, then clear any optional pins you
   do not want in the NI output. Required scan and clock pins remain selected.
4. Choose an output directory.
5. Keep **fully expand scan cycles** selected when every test cycle must be an
   ordinary one-line vector. Clear it for a much smaller `scan()`-based source.
6. Select NI compilation when Digital Pattern Compiler is installed, then click
   **Start conversion**.

You can also drag a STIL file onto the executable icon to preselect it when the
app opens.

The release executable is not code-signed, so Windows SmartScreen may display a
warning. Verify the published SHA-256 checksum before running it.

## Install

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Usage

Generate a compact NI scan pattern, timing sheet, and logical pin map:

```bash
stil-to-ni input.stil -o out
```

Also generate a fully expanded source with one vector per cycle:

```bash
stil-to-ni input.stil -o out --expand-scan
```

Compile generated pattern sources when NI Digital Pattern Compiler is installed:

```powershell
stil-to-ni input.stil -o out --compile
```

Specify the compiler explicitly if it is installed elsewhere:

```powershell
stil-to-ni input.stil -o out --compile `
  --compiler "C:\Program Files\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"
```

Convert only selected pins (required scan and clock pins must be included):

```powershell
stil-to-ni input.stil -o out --pins PA0,PA1,PA2,PA3,PA4,PA5,PA7,PA8,PA9
```

The generated logical pin map intentionally contains no PXI resource, site, or
channel assignments. Add those station-specific connections in Digital Pattern
Editor before running on hardware.

## Output model

STIL allows a waveform character such as `P` to select a pin-specific waveform.
NI pattern symbols and timing formats express this differently. The converter
creates separate timesets as needed:

```text
STIL static input     -> NI DriveNonReturn timeset
SCLK: D/U/D at edges  -> NI ReturnToLow timeset, vector symbol 1
CSN:  U/D/U at edges  -> NI ReturnToHigh timeset, vector symbol 0
STIL H/L/X output     -> NI H/L/X with CompareStrobe
STIL compare-T event  -> reject by default; explicit midband policy maps to NI M
STIL compare-V event  -> NI V (compare valid)
```

A STIL shift such as a 3,013-bit scan operation becomes either one compact
`scan(3013)` block or 3,013 ordinary vector statements with `--expand-scan`.
Parallel chains share one `scan(max_length)` operation. Shorter chains receive
a leading ScanIn filler and trailing ScanOut filler from the effective context
before the first placeholder. An absent parameter holds that context throughout
the shift. ScanIn X cycles (and ScanOut states outside H/L/X) are emitted as
ordinary vectors because NI scan strings cannot encode them. No cycles are added.

## P2506 maintenance profile

Use a **new empty output directory** for each build. The explicit profile binds
to the source SHA-256 from the 2026-10-14 maintenance report:

```powershell
stil-to-ni P2506_TOP_stuck.scan.stil -o out-p2506 --profile p2506-20261014 --expand-scan --compile
```

The profile selects PA0–PA15 and NRST, preserves Fixed with diagnostics, maps
compare-high-Z to M, and drives NRST low only during the guarded `test_setup`
macro (186 cycles). Cycle 186 resumes original NRST=X. It never aliases por to
NRST. A changed input hash, macro range, original state or resume boundary fails.
The profile hash covers the uncompressed `.stil` file bytes; use that baseline
file rather than a `.gz` wrapper. `--time-scale 10` scales every timing field
exactly and leaves vector order/state unchanged, including the PWD PA5 clock.

For other projects the defaults are strict. Deliberate exceptions can be selected
with `--fixed-policy preserve_fixed_with_diagnostic` and `--high-z-policy midband`.
The P2506 profile owns these two policies when selected. Its hardware results,
T/M electrical equivalence and station load status remain unknown until tested.
See [maintenance notes](docs/MAINTENANCE_20261014.md).

## Supported STIL subset

- `Signals` with scalar `In`, `Out`, and `InOut` pins
- ordered `SignalGroups` using `+`
- numeric nanosecond periods and edge times
- static `0`, `1`, `H`, `L`, `X`, `Z`, and `N` behavior
- three-edge `P` waveforms (`D/U/D` and `U/D/U`)
- one or more parallel `ScanChain` definitions, including unequal lengths
- `Procedures`, `MacroDefs`, `W`, `C`, `V`, `Call`, `Macro`, and `Shift`
- TetraMAX `#` parameter substitution
- TetraMAX `\r` repeat and the leading `\j` marker on already flattened single-plane values
- procedure-local `F` constraints and explicit conflict diagnostics
- optional TetraMAX cycle-summary validation

Currently unsupported:

- STIL domains and selectors
- loops, goto/match loops, and arbitrary control flow
- nested shift blocks
- multiple vectors per Shift, embedded joins and multi-plane WFCMap evaluation
- multiple compare strobes/pulse shapes per pin in one WFT
- multi-bit buses declared directly in `Signals`
- non-nanosecond or formula-based STIL timing expressions
- automatic voltage-level generation
- physical PXI channel assignment

## Safety and validation

Pattern conversion can damage hardware or produce false test results if timing,
levels, or pin mappings are wrong. Always review generated files in NI Digital
Pattern Editor, validate against simulation/golden vectors, and begin hardware
debug with safe voltage/current limits.

NI notes that third-party pattern conversion output must be verified for
accuracy; see [Supported Pattern Conversion Tools with PXI Digital Pattern Instruments](https://www.ni.com/en/support/documentation/supplemental/16/supported-pattern-conversion-tools-with-pxi-digital-pattern-inst.html).

The NI compiler is proprietary and is not included in this repository. The
project's CI validates conversion structure and cycle preservation using
synthetic fixtures. Hardware and compiler validation must be performed in an NI
development environment. This maintenance additionally exercised local NI 19.0
compilation; it does not establish compatibility or PASS on another station.

## Build the Windows app

Create a Windows virtual environment with Python 3.10 or later, then run:

```powershell
python -m pip install ".[gui]" pyinstaller
.\scripts\build_windows.ps1
```

The executable is written to `packaging/dist/STIL-to-NI-Digital.exe`.

## License

MIT. This project is independent and is not affiliated with or endorsed by
National Instruments or Synopsys. NI, NI-Digital, TetraMAX, and other product
names are trademarks of their respective owners.
