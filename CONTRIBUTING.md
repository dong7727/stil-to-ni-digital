# Contributing

Issues and pull requests are welcome. Please include a small, non-confidential
STIL fixture that demonstrates the behavior you want to add or fix.

Before submitting a pull request:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Do not submit proprietary production patterns, netlists, scan-cell names, pin
maps, or device-specific electrical limits. Minimize test data to a synthetic
reproducer.

New STIL constructs must fail safely when they cannot be translated without a
semantic change. A warning is not enough for a lossy conversion.
