# Changelog

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
