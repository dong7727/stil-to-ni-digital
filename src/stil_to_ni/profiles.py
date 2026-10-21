"""Explicit, version-bound project exceptions; never inferred from file names."""

P2506 = {
    "name": "p2506-20261014",
    "source_sha256": "71cc957ffd53815c253c9f85716aa1f98d08fb14bca4e925e44a48290b583ffc",
    "fixed_policy": "preserve_fixed_with_diagnostic",
    "high_z_policy": "midband",
    "pins": [f"PA{i}" for i in range(16)] + ["NRST"],
    "entry": {
        "macro": "test_setup", "invocation_index": 0, "expected_instances": 1,
        "expected_start_cycle": 0, "expected_cycles": 186,
        "pin": "NRST", "expected_ni_state": "X", "replacement_ni_state": "0",
        "boundary_label": "pattern_0", "boundary_ni_state": "X",
        "basis": "user_confirmed_station_requirement_2026-10-13",
    },
}

PROFILES = {P2506["name"]: P2506}
