"""Independent comparison of expanded NI sources, including active timing events.

This reader does not import the converter and rejects compact/control-flow input.
Timing-file equivalence is not a hardware/electrical-equivalence assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from itertools import zip_longest
from pathlib import Path

NS = {'n': 'http://www.ni.com/Semiconductor/Timing'}


def ns(value):
    value = value.strip()
    return Decimal(value[:-2].strip()) if value.endswith('ns') else Decimal(value) * Decimal(10**9)


class Reader:
    def __init__(self, source, timing):
        self.source = source
        self.labels = {}
        self.pins = []
        self.cache = {}
        self.timing = {}
        self.m_positions = []
        for ts in ET.parse(timing).findall('.//n:TimeSet', NS):
            edges = {}
            for pin in ts.findall('n:PinEdges/n:PinEdge', NS):
                drive = pin[0]
                edges[pin.attrib['pin']] = (drive.tag.split('}')[-1],
                    {child.tag.split('}')[-1]: ns(child.text) for child in drive},
                    ns(pin.findtext('n:CompareStrobe/n:Strobe', namespaces=NS)))
            self.timing[ts.attrib['name']] = ns(ts.findtext('n:Period', namespaces=NS)), edges

    def canonical(self, timeset, data):
        key = (timeset, data)
        if key in self.cache:
            return self.cache[key]
        period, edges = self.timing[timeset]
        result = [period]
        for pin, symbol in zip(self.pins, data):
            mode, times, strobe = edges[pin]
            if symbol == 'X':
                result.append(('masked',))
            elif symbol in 'HLMV':
                result.append(('compare', symbol, strobe))
            elif symbol in '01':
                active = (mode == 'ReturnToLow' and symbol == '1') or (mode == 'ReturnToHigh' and symbol == '0')
                if active:
                    result.append(('pulse', mode, times['On'], times['Data'], times['Return'], times['Off']))
                elif mode in ('ReturnToLow', 'ReturnToHigh', 'DriveNonReturn'):
                    result.append(('drive', symbol, times['On'], Decimal(0) if mode != 'DriveNonReturn' else times['Data'], times['Off']))
                else:
                    raise ValueError(f'unsupported drive format {mode}')
            else:
                raise ValueError(f'unsupported pin state {symbol}')
        self.cache[key] = tuple(result)
        return self.cache[key]

    def rows(self):
        active = False
        count = 0
        halted = False
        with self.source.open(encoding='utf-8-sig') as stream:
            for line in stream:
                code = line.split('//', 1)[0].strip()
                if not code:
                    continue
                if code.startswith('pattern '):
                    self.pins = [pin.strip() for pin in re.search(r'\(([^)]+)\)', code)[1].split(',')]
                elif code == '{':
                    if active:
                        raise ValueError('compact scan is not accepted by this reader')
                    active = True
                elif code == '}':
                    active = False
                elif active and code.endswith(':'):
                    self.labels[code[:-1]] = count
                elif active:
                    if halted:
                        raise ValueError('vector after halt')
                    tokens = code.rstrip(';').split()
                    if tokens[0] == 'halt':
                        halted = True
                        tokens.pop(0)
                    timeset, *data = tokens
                    if len(data) != len(self.pins):
                        raise ValueError(f'invalid vector at cycle {count}')
                    self.m_positions.extend([count, pin] for pin, char in zip(self.pins, data) if char == 'M')
                    yield self.canonical(timeset, tuple(data)), halted
                    count += 1
        if not halted:
            raise ValueError('missing final halt')


def compare(left, left_timing, right, right_timing):
    a, b = Reader(left, left_timing), Reader(right, right_timing)
    mismatches, examples, count = 0, [], 0
    for cycle, (x, y) in enumerate(zip_longest(a.rows(), b.rows())):
        count += 1
        if a.pins != b.pins:
            raise ValueError('pin order differs')
        if x != y:
            mismatches += 1
            if len(examples) < 10:
                examples.append({'cycle': cycle, 'left': str(x), 'right': str(y)})
    shared = a.labels.keys() & b.labels.keys()
    label_mismatches = {key: [a.labels[key], b.labels[key]] for key in shared if a.labels[key] != b.labels[key]}
    missing_scan_labels = [label for label in a.labels.keys() ^ b.labels.keys() if re.fullmatch(r'pattern_\d+', label)]
    return {'cycles': count, 'pins': a.pins, 'mismatched_cycles': mismatches, 'examples': examples,
            'common_labels': len(shared), 'label_mismatches': label_mismatches,
            'missing_scan_labels': missing_scan_labels,
            'labels_only_left': sorted(a.labels.keys() - b.labels.keys()),
            'labels_only_right': sorted(b.labels.keys() - a.labels.keys()),
            'm_positions_match': a.m_positions == b.m_positions, 'm_positions': a.m_positions,
            'ok': not mismatches and not label_mismatches and not missing_scan_labels and a.m_positions == b.m_positions,
            'scope': 'All expanded cycles: pin order, drive/compare/pulse events, period, halt, shared labels. No hardware claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for name in ('left', 'left-timing', 'right', 'right-timing', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.left, args.left_timing, args.right, args.right_timing)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('ok', 'cycles', 'mismatched_cycles', 'common_labels', 'label_mismatches', 'missing_scan_labels')}, ensure_ascii=True))
    raise SystemExit(0 if result['ok'] else 1)
