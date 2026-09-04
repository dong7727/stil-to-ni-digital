# Changelog

## 0.3.0 - 2026-09-04

- Support multiple parallel STIL scan chains, including unequal chain lengths.
- Emit NI multi-scan declarations verified with Digital Pattern Compiler 19.0.
- Expand TetraMAX `\r`/`\j` compact WFC assignments and process `F` statements.
- Map STIL compare-valid `T` waveforms to NI `V` pin states.
- Inspect STIL metadata before conversion and let desktop users select output pins.
- Keep ScanIn, ScanOut, scan-clock, and pulse-waveform pins mandatory when filtering.
- Add the CLI `--pins` option and record selected/omitted pins in the report.

## 0.2.1 - 2026-09-04

- Replace the Tk desktop runtime with Qt for reliable startup from non-ASCII
  Windows paths.
- Pin the GUI toolkit and the Python stable-ABI DLL used by packaged builds.
- Strengthen packaged executable smoke tests to enter and exit the GUI event
  loop and fail on startup errors.

## 0.2.0 - 2026-09-04

- Add a Windows desktop interface with file selection and drag-and-drop input.
- Run conversion in a background thread with status and log output.
- Detect the NI Digital Pattern Compiler and optionally create `.digipat` files.
- Add a reproducible PyInstaller build and packaged-executable smoke test.

## 0.1.0 - 2026-09-04

- Initial open-source release.
- Convert a practical TetraMAX scan STIL subset to `.digipatsrc`, `.digitiming`,
  and logical `.pinmap` files.
- Preserve scan shifts as NI `scan()` blocks.
- Optionally expand scan shifts to one ordinary vector per test cycle.
- Optionally compile patterns with an installed NI Digital Pattern Compiler.
- Validate source-reported test-cycle counts when present.
