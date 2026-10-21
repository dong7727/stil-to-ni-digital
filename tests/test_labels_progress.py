from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from stil_to_ni.cli import build_parser
from stil_to_ni.compiler import compile_pattern
from stil_to_ni.converter import ConversionError, convert_file

MINIMAL = (Path(__file__).parent / 'fixtures/minimal_scan.stil').read_text()


class LabelsProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'input.stil'

    def write_calls(self, count):
        header = MINIMAL.split('Pattern "main" {')[0]
        calls = '\n'.join(
            f'"pattern_{i}": Call "load_unload" {{ "SDI"=0101; }}' for i in range(count)
        )
        self.source.write_text(header + 'Pattern "main" {\n' + calls + '\n}', encoding='utf-8')

    def test_auto_at_compiler_limit_and_overflow_preserves_cycles_and_index(self):
        for count in (8191, 8192):
            with self.subTest(count=count):
                self.write_calls(count)
                events = []
                result = convert_file(self.source, self.root / str(count),
                                      expand_scan=True,
                                      progress=lambda p, s: events.append((p, s)))
                text = result.files['pattern_source'].read_text()
                self.assertEqual(text.count(':\n'), count if count == 8191 else 0)
                self.assertEqual(result.cycles, count * 5)
                with result.files['label_index'].open(newline='') as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), count)
                self.assertEqual(rows[-1], {'label': f'pattern_{count - 1}',
                                           'execution_cycle_0based': str((count - 1) * 5)})
                percentages = [p for p, _ in events]
                self.assertEqual(percentages, sorted(percentages))
                self.assertEqual((percentages[0], percentages[-1]), (0, 100))
                self.assertGreater(len(set(percentages)), 30)
                self.assertTrue(any(75 < p < 95 and s == '写入展开 Pattern' for p, s in events))

    def test_explicit_keep_overflow_fails_before_writing_and_never_reports_success(self):
        self.write_calls(8192)
        events = []
        with self.assertRaisesRegex(ConversionError, '8192.*8191'):
            convert_file(self.source, self.root / 'out', keep_labels=True,
                         progress=lambda p, s: events.append(p))
        self.assertFalse((self.root / 'out').exists())
        self.assertNotIn(100, events)

    def test_omit_labels_changes_only_label_lines_in_both_formats(self):
        self.write_calls(10)
        keep = convert_file(self.source, self.root / 'keep', keep_labels=True, expand_scan=True)
        omit = convert_file(self.source, self.root / 'omit', keep_labels=False, expand_scan=True)
        for key in ('pattern_source', 'expanded_pattern_source'):
            before = keep.files[key].read_text().splitlines()
            after = omit.files[key].read_text().splitlines()
            self.assertEqual([line for line in before if not line.endswith(':')], after)
        self.assertEqual(keep.cycles, omit.cycles)

    def test_cli_defaults_to_auto(self):
        parser = build_parser()
        base = ['input.stil', '-o', 'out']
        self.assertIsNone(parser.parse_args(base).keep_labels)
        self.assertIs(parser.parse_args(base + ['--no-labels']).keep_labels, False)
        self.assertIs(parser.parse_args(base + ['--keep-labels']).keep_labels, True)

    def test_compiler_reports_completion_only_after_readback_matches(self):
        source = self.root / 'input.digipatsrc'
        source.write_text('halt ts 0;\n')
        binary = self.root / 'input.digipat'
        readback = self.root / 'input.readback.digipatsrc'
        for content, matches in [('halt ts 0;\n', True), ('halt ts 1;\n', False)]:
            readback.write_text(content)
            events = []
            with patch('stil_to_ni.compiler.find_compiler', return_value=Path('compiler')), \
                 patch('stil_to_ni.compiler.subprocess.run',
                       return_value=CompletedProcess([], 0, '', '')):
                if matches:
                    compile_pattern(source, self.root / 'pins', binary,
                                    progress=lambda p, s: events.append(p))
                    self.assertEqual(events[-1], 100)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'round-trip'):
                        compile_pattern(source, self.root / 'pins', binary,
                                        progress=lambda p, s: events.append(p))
                    self.assertNotIn(100, events)


if __name__ == '__main__':
    unittest.main()
