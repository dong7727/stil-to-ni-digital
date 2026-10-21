# Changelog

## 0.4.1 - 2026-10-21

- Default to automatic labels: omit call-location labels when their count exceeds
  the NI compiler's 8191-label limit. Always export a zero-based cycle index CSV.
- Add GUI label selection and CLI `--keep-labels`; explicit keep fails before
  writing when the limit is exceeded. `--no-labels` remains supported.
- Display overall conversion, writing, compilation and readback progress in the
  GUI and with CLI `--progress`. External compiler stages hold their percentage
  until the tool returns; 100% requires successful requested validation.
- Avoid repeated copies and line counting over the entire Pattern body.
- Package source from the current checkout instead of an older installed wheel;
  verify packaged Python bytecode against the checkout before publishing.
- Add boundary, waveform-preservation, progress and readback regressions.

## 0.4.0 - 2026-10-14

- Derive unequal-chain input/output padding and absent parameters from pre-shift
  context; preserve valid bit order without applying ScanInversion twice.
- Split input X and non-H/L/X output cycles out of NI compact scan blocks.
- Enforce procedure-local Fixed constraints; default to error on conflicts and
  record source assignment/cycle/call under an explicit preservation policy.
- Correct the former T-to-V assumption: resolve waveform events per WFT/pin;
  compare-high-Z requires an explicit M policy and station electrical validation.
- Add guarded P2506 setup-only NRST override, exact Decimal timing scaling,
  GUI profile/time-scale selection, and macro/PWD timeline export.
- Require empty build directories; record hashes and separate validation stages.
- Compile and decompile with the official compiler and verify normalized source.
- Reject unsupported executable statements and embedded join expressions.
- Add synthetic regressions and an independent expanded NI waveform comparator.
- Keep all desktop options accessible through a scrollable layout on smaller windows.

## 0.3.0 - 2026-09-04

- Support multiple parallel STIL scan chains, including unequal chain lengths.
- Emit NI multi-scan declarations verified with Digital Pattern Compiler 19.0.
- Expand TetraMAX `\r`/`\j` compact WFC assignments and process `F` statements.
- Previously mapped `T` to NI `V`; this incorrect assumption is fixed in 0.4.0.
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
