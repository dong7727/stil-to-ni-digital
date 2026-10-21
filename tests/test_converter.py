from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stil_to_ni.converter import ConversionError, convert_file, inspect_file


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_scan.stil"
MULTI_FIXTURE = Path(__file__).parent / "fixtures" / "multi_scan.stil"


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

    def test_multiple_unequal_scan_chains(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = convert_file(MULTI_FIXTURE, Path(directory), expand_scan=True, high_z_policy='midband')
            self.assertEqual(result.cycles, 16)
            self.assertEqual(result.scan_instructions, 3)
            source = result.files["pattern_source"].read_text(encoding="utf-8")
            self.assertIn("scan_in SI0, SI1;", source)
            self.assertIn("scan_out SO0, SO1;", source)
            self.assertIn("SI1 0101;", source)
            self.assertIn("SO1 LHLX;", source)
            self.assertIn("default_WFT_CLK_P 1 0 1 1 1 M M;", source)
            expanded = result.files["expanded_pattern_source"].read_text(encoding="utf-8")
            self.assertNotIn("scan(", expanded)

    def test_inspection_and_pin_selection(self) -> None:
        inspection = inspect_file(MULTI_FIXTURE)
        self.assertEqual(len(inspection.scan_chains), 2)
        self.assertEqual([chain.length for chain in inspection.scan_chains], [4, 3])
        required = {pin.name for pin in inspection.pins if pin.required}
        self.assertEqual(required, {"CLK", "SI0", "SI1", "SO0", "SO1"})

        with tempfile.TemporaryDirectory() as directory:
            selected = ["CLK", "SI0", "SI1", "AUX", "SO0", "SO1"]
            result = convert_file(MULTI_FIXTURE, Path(directory), selected_pins=selected, high_z_policy='midband')
            self.assertEqual(result.pins, tuple(selected))
            source = result.files["pattern_source"].read_text(encoding="utf-8")
            timing = result.files["timing"].read_text(encoding="utf-8")
            pinmap = result.files["pinmap"].read_text(encoding="utf-8")
            report = result.files["report"].read_text(encoding="utf-8")
            self.assertIn("pattern multi (CLK, SI0, SI1, AUX, SO0, SO1)", source)
            self.assertNotIn('<PinEdge pin="CAP">', timing)
            self.assertNotIn('<DUTPin name="CAP"', pinmap)
            self.assertIn("Omitted pins: CAP", report)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConversionError, "required scan/clock pins"):
                convert_file(MULTI_FIXTURE, Path(directory), selected_pins=["CLK", "SI0"], high_z_policy='midband')


if __name__ == "__main__":
    unittest.main()
