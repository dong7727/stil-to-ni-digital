from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from stil_to_ni.converter import ConversionError, convert_file, _sha256

FIXTURES = Path(__file__).parent / 'fixtures'
MINIMAL = (FIXTURES / 'minimal_scan.stil').read_text()
MULTI = (FIXTURES / 'multi_scan.stil').read_text()
NS = {'n': 'http://www.ni.com/Semiconductor/Timing'}


def vectors(text):
    return [line.rstrip(';').split() for line in text.splitlines()
            if line.endswith(';') and not line.startswith(('file_format_version', 'timeset'))]


class SemanticsTests(unittest.TestCase):
    def run_text(self, text, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / 'input.stil'
        source.write_text(text, encoding='utf-8')
        return convert_file(source, source.parent / 'out', expand_scan=True, **kwargs)

    def test_short_input_uses_context_and_missing_arguments_hold_context(self):
        text = MULTI.replace('"all_inputs" { 1', '"all_inputs" { Z { \'0ns\' Z; } }\n      "all_inputs" { 1')
        text = text.replace('"all_outputs"=\\r2 X; }\n    F', '"all_outputs"=\\r2 X; "SI1"=Z; }\n    F')
        result = self.run_text(text, high_z_policy='midband')
        compact = result.files['pattern_source'].read_text()
        self.assertIn('SI1 101;', compact)
        self.assertIn('SI1 010;', compact)
        self.assertNotIn('SI1 X', compact)  # NI scan strings cannot contain X inputs
        expanded = vectors(result.files['expanded_pattern_source'].read_text())
        self.assertEqual(''.join(v[4] for v in expanded[1:5]), 'X101')
        self.assertEqual(''.join(v[4] for v in expanded[12:15]) + expanded[15][5], 'XXXX')
        self.assertTrue(all(v[6:] == ['X', 'X'] for v in expanded[1:5]))

    def test_scanout_padding_uses_context_not_forced_mask(self):
        text = MULTI.replace('"all_outputs"=\\r2 X; }\n    F', '"all_outputs"=\\r2 H; }\n    F')
        result = self.run_text(text, high_z_policy='midband')
        self.assertIn('SO1 LHLH;', result.files['pattern_source'].read_text())

    def test_fixed_conflict_strict_and_preserved_empty_vectors(self):
        text = MINIMAL.replace('"capture" {\n', '"capture" {\n    F { "AUX"=1; }\n')
        with self.assertRaisesRegex(ConversionError, 'Fixed conflict.*AUX'):
            self.run_text(text)
        result = self.run_text(text, fixed_policy='preserve_fixed_with_diagnostic')
        rows = vectors(result.files['expanded_pattern_source'].read_text())
        self.assertTrue(all(row[4] == '1' for row in rows[7:15]))
        diagnostics = json.loads(result.files['diagnostics'].read_text())
        self.assertEqual(len([d for d in diagnostics if d['kind'] == 'fixed_conflict']), 8)
        self.assertEqual(result.cycles, 20)  # F/C/W add no cycles; empty V does.
        self.assertTrue(all(d['assignment']['line'] > 0 for d in diagnostics if d['kind'] == 'fixed_conflict'))

    def test_fixed_does_not_constrain_next_invocation(self):
        text = MINIMAL.replace('"setup" {\n', '"setup" {\n    F { "AUX"=0; }\n')
        result = self.run_text(text)
        rows = vectors(result.files['expanded_pattern_source'].read_text())
        self.assertEqual(rows[1][4], '0')
        self.assertEqual(rows[2][4], '1')

    def test_T_requires_explicit_midband_not_compare_valid(self):
        with self.assertRaisesRegex(ConversionError, 'compare-high-Z'):
            self.run_text(MULTI)
        result = self.run_text(MULTI, high_z_policy='midband')
        rows = vectors(result.files['expanded_pattern_source'].read_text())
        self.assertEqual(rows[5][-2:], ['M', 'M'])
        valid = MULTI.replace("'40ns' T;", "'40ns' V;")
        result = self.run_text(valid)
        self.assertEqual(vectors(result.files['expanded_pattern_source'].read_text())[5][-2:], ['V', 'V'])

    def test_waveform_table_specific_edges_and_exact_scale(self):
        head, capture = MINIMAL.split('WaveformTable "capture_WFT"')
        text = head + 'WaveformTable "capture_WFT"' + capture.replace("'40ns'", "'32.125ns'").replace("'45ns'", "'46.125ns'")
        result = self.run_text(text, time_scale='10')
        xml = ET.parse(result.files['timing'])
        for ts in xml.findall('.//n:TimeSet', NS):
            self.assertEqual(ts.findtext('n:Period', namespaces=NS), '1000 ns')
            capture = ts.attrib['name'].startswith('capture')
            out = ts.find('n:PinEdges/n:PinEdge[@pin="SDOB"]/n:CompareStrobe/n:Strobe', NS)
            self.assertEqual(out.text, '321.25 ns' if capture else '400 ns')
            for edge in ts.findall('.//n:ReturnToLow/n:Data', NS) + ts.findall('.//n:ReturnToHigh/n:Data', NS):
                self.assertEqual(edge.text, '461.25 ns' if capture else '450 ns')

    def test_all_times_scale_without_vector_changes(self):
        one = self.run_text(MINIMAL)
        ten = self.run_text(MINIMAL, time_scale='10')
        self.assertEqual(one.files['expanded_pattern_source'].read_bytes(), ten.files['expanded_pattern_source'].read_bytes())
        a = list(ET.parse(one.files['timing']).iter())
        b = list(ET.parse(ten.files['timing']).iter())
        fields = {'Period', 'On', 'Data', 'Off', 'Strobe', 'Return'}
        for x, y in zip(a, b):
            if x.tag.split('}')[-1] in fields:
                self.assertEqual(Decimal(y.text.split()[0]), Decimal(x.text.split()[0]) * 10)

    def test_guarded_entry_override_and_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.stil'
            source.write_text(MINIMAL)
            profile = {'name': 'synthetic', 'source_sha256': _sha256(source), 'fixed_policy': 'error',
                       'high_z_policy': 'error', 'pins': ['CSN', 'SDI', 'SCLK', 'AUX', 'SDOB'],
                       'entry': {'macro': 'setup', 'invocation_index': 0, 'expected_instances': 1,
                                 'expected_start_cycle': 0, 'expected_cycles': 2, 'pin': 'AUX',
                                 'expected_ni_state': '0', 'replacement_ni_state': '1',
                                 'boundary_label': 'pattern_0', 'boundary_ni_state': '1', 'basis': 'test'}}
            with patch('stil_to_ni.converter.PROFILES', {'synthetic': profile}):
                result = convert_file(source, Path(folder) / 'ok', project_profile='synthetic', expand_scan=True, keep_labels=False)
                rows = vectors(result.files['expanded_pattern_source'].read_text())
                self.assertEqual([r[4] for r in rows[:3]], ['1', '1', '1'])
                self.assertEqual(rows[7][4], '0')
                for field, bad in [('expected_cycles', 3), ('expected_instances', 2), ('expected_ni_state', 'X'), ('boundary_label', 'missing')]:
                    original = profile['entry'][field]
                    profile['entry'][field] = bad
                    with self.assertRaisesRegex(ConversionError, 'entry override'):
                        convert_file(source, Path(folder) / field, project_profile='synthetic')
                    profile['entry'][field] = original
                source.write_text(MINIMAL + '\n')
                with self.assertRaisesRegex(ConversionError, 'SHA-256 mismatch'):
                    convert_file(source, Path(folder) / 'hash', project_profile='synthetic')

    def test_comments_do_not_execute_but_unsupported_control_flow_rejected(self):
        result = self.run_text(MINIMAL.replace('Macro "setup";', '/* V { "AUX"=1; } } */\n Macro "setup";'))
        self.assertEqual(result.cycles, 20)
        for text in [MINIMAL.replace('Macro "setup";', 'Loop 2 { V {} }'),
                     MINIMAL.replace('V { "SCLK"=0; }', 'Loop 2 { V {} }'),
                     MINIMAL.replace('"_pi"=1000;', '"_pi"=10\\j 00;'),
                     MINIMAL.replace("'45ns' U;", "'45ns' H;")]:
            with self.subTest(text=text[-40:]), self.assertRaises(ConversionError):
                self.run_text(text)

    def test_invalid_scale_and_existing_output_rejected(self):
        for scale in ['0', '-1', 'NaN', 'Infinity', 'bad']:
            with self.subTest(scale=scale), self.assertRaises(ConversionError):
                self.run_text(MINIMAL, time_scale=scale)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'keep.txt').write_text('keep')
            with self.assertRaisesRegex(ConversionError, 'must be empty'):
                convert_file(FIXTURES / 'minimal_scan.stil', Path(folder))
            self.assertEqual((Path(folder) / 'keep.txt').read_text(), 'keep')

    def test_manifest_does_not_claim_hardware_validation(self):
        result = self.run_text(MINIMAL)
        manifest = json.loads(result.files['manifest'].read_text())
        self.assertEqual(manifest['cycles'], 20)
        self.assertEqual(manifest['config']['project_profile'], {})
        self.assertEqual(manifest['validation']['hardware_burst_result'], 'unknown')
        for kind, record in manifest['files'].items():
            self.assertEqual(record['sha256'], _sha256(result.files[kind]))

    def test_one_cycle_final_scan_gets_halt_without_extra_cycle(self):
        text = MINIMAL.replace('ScanLength 4;', 'ScanLength 1;').replace('"SDI"=0101;', '"SDI"=1;').replace('"SDOB"=LHXL;', '"SDOB"=L;').replace('generating 20 test cycles', 'generating 14 test cycles')
        result = self.run_text(text)
        rows = vectors(result.files['expanded_pattern_source'].read_text())
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[-1][0], 'halt')
        self.assertEqual(rows[-1][-1], 'L')

    def test_fixed_conflict_inside_shift_is_not_ignored(self):
        text = MULTI.replace('"CLK"=P; "_si"', '"AUX"=0; "CLK"=P; "_si"')
        with self.assertRaisesRegex(ConversionError, 'Fixed conflict.*AUX'):
            self.run_text(text, high_z_policy='midband')

    def test_group_subtraction_is_rejected(self):
        text = MINIMAL.replace("'\"SCLK\" + \"CSN\"'", "'\"SCLK\" - \"CSN\"'")
        with self.assertRaisesRegex(ConversionError, 'group expression'):
            self.run_text(text)


if __name__ == '__main__':
    unittest.main()
