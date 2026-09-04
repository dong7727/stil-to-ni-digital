from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stil_to_ni.converter import convert_file


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_scan.stil"


class ConverterTests(unittest.TestCase):
    def test_reserved_pattern_name_is_escaped(self) -> None:
        source_text = FIXTURE.read_text(encoding="utf-8").replace(
            'Pattern "main" {', 'Pattern "_pattern_" {'
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reserved.stil"
            source.write_text(source_text, encoding="utf-8")
            result = convert_file(source, Path(directory) / "out")
            pattern = result.files["pattern_source"].read_text(encoding="utf-8")
            self.assertIn("pattern id_pattern (", pattern)

    def test_compact_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = convert_file(FIXTURE, Path(directory))
            self.assertEqual(result.pins, ("CSN", "SDI", "SCLK", "AUX", "SDOB"))
            self.assertEqual(result.cycles, 20)
            self.assertEqual(result.scan_instructions, 2)
            source = result.files["pattern_source"].read_text(encoding="utf-8")
            self.assertEqual(source.count("scan("), 2)
            self.assertIn("scan(4) default_WFT_SCLK_P 1 _ 1 1 _;", source)
            self.assertIn("SDOB XXXX;", source)
            self.assertTrue(source.rstrip().endswith("}"))

    def test_expanded_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = convert_file(FIXTURE, Path(directory), expand_scan=True)
            source = result.files["expanded_pattern_source"].read_text(encoding="utf-8")
            self.assertNotIn("scan(", source)
            vector_lines = [
                line for line in source.splitlines()
                if line.endswith(";") and not line.startswith(("file_format_version", "timeset"))
            ]
            self.assertEqual(len(vector_lines), 20)
            self.assertEqual(sum(line.startswith("halt ") for line in vector_lines), 1)

    def test_timing_pulses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = convert_file(FIXTURE, Path(directory))
            timing = result.files["timing"].read_text(encoding="utf-8")
            self.assertIn("<ReturnToLow>", timing)
            self.assertIn("<ReturnToHigh>", timing)
            self.assertIn("<Strobe>40 ns</Strobe>", timing)


if __name__ == "__main__":
    unittest.main()
