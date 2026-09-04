"""Converter for a practical, documented subset of scan-oriented STIL.

This module intentionally fails on unsupported constructs instead of silently
changing test semantics. It is not a complete IEEE 1450 parser.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


class ConversionError(ValueError):
    """Raised when input uses a STIL construct this converter cannot preserve."""


NI_RESERVED_IDENTIFIERS = {
    "capture_start",
    "capture_stop",
    "halt",
    "pattern",
    "repeat",
    "scan",
    "scan_in",
    "scan_out",
    "source",
    "timeset",
}


@dataclass
class VectorOp:
    timeset: str
    values: list[str]
    label: str | None = None
    opcode: str = ""

    @property
    def cycles(self) -> int:
        return 1


@dataclass
class ScanOp:
    timeset: str
    count: int
    base_values: list[str]
    sequences: dict[str, str]
    label: str | None = None

    @property
    def cycles(self) -> int:
        return self.count


@dataclass
class DefinitionEvent:
    kind: str
    payload: object


@dataclass
class Model:
    source: Path
    output_dir: Path
    pins: list[str] = field(default_factory=list)
    directions: dict[str, str] = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)
    waveform_tables: list[str] = field(default_factory=list)
    periods_ns: dict[str, float] = field(default_factory=dict)
    compare_ns: float = 40.0
    pulse_edges: dict[str, tuple[str, float, float]] = field(default_factory=dict)
    scan_length: int = 0
    scan_in: str = ""
    scan_out: str = ""
    procedures: dict[str, list[DefinitionEvent]] = field(default_factory=dict)
    macros: dict[str, list[DefinitionEvent]] = field(default_factory=dict)
    ops: list[VectorOp | ScanOp] = field(default_factory=list)
    expected_cycles: int | None = None
    expected_v_statements: int | None = None
    used_timesets: list[str] = field(default_factory=list)
    timeset_meta: dict[str, tuple[str, tuple[str, ...]]] = field(default_factory=dict)
    pattern_name: str = "converted_pattern"


@dataclass(frozen=True)
class ConversionResult:
    files: dict[str, Path]
    pins: tuple[str, ...]
    cycles: int
    vector_instructions: int
    scan_instructions: int


def _read_text(path: Path) -> str:
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


def _balanced_end(text: str, open_pos: int) -> int:
    depth = 0
    in_quote = False
    for index in range(open_pos, len(text)):
        char = text[index]
        if char == '"' and (index == 0 or text[index - 1] != "\\"):
            in_quote = not in_quote
        if in_quote:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ConversionError("unterminated brace block")


def _extract_block(text: str, header_pattern: str) -> str:
    match = re.search(header_pattern, text, re.MULTILINE)
    if not match:
        raise ConversionError(f"missing STIL block matching {header_pattern!r}")
    open_pos = text.find("{", match.start(), match.end() + 1)
    if open_pos < 0:
        raise ConversionError(f"block has no opening brace: {header_pattern!r}")
    return text[open_pos + 1 : _balanced_end(text, open_pos)]


def _named_blocks(section_body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    pos = 0
    header = re.compile(r'^\s*"([^"]+)"\s*\{', re.MULTILINE)
    while match := header.search(section_body, pos):
        open_pos = section_body.find("{", match.start(), match.end())
        end = _balanced_end(section_body, open_pos)
        result[match.group(1)] = section_body[open_pos + 1 : end]
        pos = end + 1
    return result


def _assignments(body: str) -> dict[str, str]:
    return {
        name: re.sub(r"\s+", "", value)
        for name, value in re.findall(r'"([^"]+)"\s*=\s*([^;]+);', body, re.DOTALL)
    }


def _sanitize(value: str, fallback: str = "label") -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_") or fallback
    if value[0].isdigit():
        value = f"L_{value}"
    if value.lower() in NI_RESERVED_IDENTIFIERS:
        value = f"id_{value}"
    return value


def _fmt_ns(value: float) -> str:
    return f"{int(value)} ns" if float(value).is_integer() else f"{value:g} ns"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _output_base(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".stil.gz"):
        return name[:-8]
    if name.lower().endswith(".stil"):
        return name[:-5]
    return path.stem


def _parse_signals_groups(text: str, model: Model) -> None:
    signal_block = _extract_block(text, r"^Signals\s*\{")
    for name, direction in re.findall(r'"([^"]+)"\s+(InOut|In|Out)\b', signal_block):
        model.pins.append(name)
        model.directions[name] = direction
    if not model.pins:
        raise ConversionError("no signals found")

    group_block = _extract_block(text, r"^SignalGroups\s*\{")
    for name, expression in re.findall(
        r'"([^"]+)"\s*=\s*\'([^\']+)\'[^;]*;', group_block, re.DOTALL
    ):
        expanded: list[str] = []
        for item in re.findall(r'"([^"]+)"', expression):
            if item in model.groups:
                expanded.extend(model.groups[item])
            elif item in model.pins:
                expanded.append(item)
            else:
                raise ConversionError(f"unknown signal/group {item!r} in group {name!r}")
        model.groups[name] = expanded


def _parse_timing(text: str, model: Model) -> None:
    timing = _extract_block(text, r"^Timing\s*\{")
    pos = 0
    header = re.compile(r'WaveformTable\s+"([^"]+)"\s*\{')
    while match := header.search(timing, pos):
        name = match.group(1)
        open_pos = timing.find("{", match.start(), match.end())
        end = _balanced_end(timing, open_pos)
        body = timing[open_pos + 1 : end]
        period = re.search(r"Period\s+'([0-9.]+)ns'", body)
        if not period:
            raise ConversionError(f"waveform table {name!r} needs a numeric ns period")
        model.waveform_tables.append(name)
        model.periods_ns[name] = float(period.group(1))

        compare_edges = re.findall(
            r'\{\s*[HLT]\s*\{[^}]*\'([0-9.]+)ns\'\s*[HLT]', body, re.DOTALL
        )
        if compare_edges:
            values = {float(value) for value in compare_edges}
            if len(values) != 1:
                raise ConversionError(f"waveform table {name!r} has multiple compare strobes")
            model.compare_ns = values.pop()

        pulse_re = re.compile(
            r'"([^"]+)"\s*\{\s*P\s*\{\s*\'0ns\'\s*([DU]);\s*'
            r"'([0-9.]+)ns'\s*([DU]);\s*'([0-9.]+)ns'\s*([DU]);\s*\}\s*\}",
            re.DOTALL,
        )
        for pin, initial, data_time, data_level, return_time, return_level in pulse_re.findall(body):
            if pin not in model.pins:
                continue
            if (initial, data_level, return_level) == ("D", "U", "D"):
                mode = "ReturnToLow"
            elif (initial, data_level, return_level) == ("U", "D", "U"):
                mode = "ReturnToHigh"
            else:
                raise ConversionError(f"unsupported P waveform on pin {pin!r}")
            edge = (mode, float(data_time), float(return_time))
            if pin in model.pulse_edges and model.pulse_edges[pin] != edge:
                raise ConversionError(f"P waveform for pin {pin!r} differs across tables")
            model.pulse_edges[pin] = edge
        pos = end + 1
    if not model.waveform_tables:
        raise ConversionError("no waveform tables found")


def _parse_scan(text: str, model: Model) -> None:
    block = _extract_block(text, r"^ScanStructures\s*\{")
    lengths = re.findall(r"ScanLength\s+(\d+)\s*;", block)
    inputs = re.findall(r'ScanIn\s+"([^"]+)"\s*;', block)
    outputs = re.findall(r'ScanOut\s+"([^"]+)"\s*;', block)
    if len(lengths) != 1 or len(inputs) != 1 or len(outputs) != 1:
        raise ConversionError("exactly one scan chain is currently supported")
    model.scan_length = int(lengths[0])
    model.scan_in = inputs[0]
    model.scan_out = outputs[0]


def _definition_events(body: str) -> list[DefinitionEvent]:
    events: list[DefinitionEvent] = []
    pos = 0
    token_re = re.compile(r"\b(W|C|V|Shift)\b")
    while match := token_re.search(body, pos):
        kind = match.group(1)
        if kind == "W":
            wft = re.match(r'W\s+"([^"]+)"\s*;', body[match.start() :])
            if not wft:
                raise ConversionError("malformed W statement in definition")
            events.append(DefinitionEvent("W", wft.group(1)))
            pos = match.start() + wft.end()
            continue
        open_pos = body.find("{", match.end())
        if open_pos < 0:
            raise ConversionError(f"malformed {kind} block")
        end = _balanced_end(body, open_pos)
        inner = body[open_pos + 1 : end]
        payload: object = _definition_events(inner) if kind == "Shift" else _assignments(inner)
        events.append(DefinitionEvent(kind, payload))
        pos = end + 1
    return events


def _parse_definitions(text: str, model: Model) -> None:
    procedures = _named_blocks(_extract_block(text, r"^Procedures\s*\{"))
    model.procedures = {name: _definition_events(body) for name, body in procedures.items()}
    try:
        macros = _named_blocks(_extract_block(text, r"^MacroDefs\s*\{"))
    except ConversionError:
        macros = {}
    model.macros = {name: _definition_events(body) for name, body in macros.items()}


def _target_pins(model: Model, target: str) -> list[str]:
    pins = model.groups.get(target, [target])
    if any(pin not in model.pins for pin in pins):
        raise ConversionError(f"assignment targets unknown pin/group {target!r}")
    return pins


def _apply(
    model: Model,
    state: dict[str, str],
    assignments: dict[str, str],
    params: dict[str, str] | None = None,
) -> None:
    params = params or {}
    for target, template in assignments.items():
        pins = _target_pins(model, target)
        if len(template) != len(pins):
            raise ConversionError(
                f"assignment width mismatch for {target!r}: got {len(template)}, expected {len(pins)}"
            )
        parameter = params.get(target)
        if parameter is not None and len(parameter) != len(pins):
            raise ConversionError(f"call parameter width mismatch for {target!r}")
        for index, (pin, symbol) in enumerate(zip(pins, template)):
            if symbol == "#":
                if parameter is not None:
                    symbol = parameter[index]
                elif pin in params and len(params[pin]) == 1:
                    symbol = params[pin]
                else:
                    symbol = state[pin]
            state[pin] = symbol


def _timeset_name(model: Model, wft: str, pulse_pins: Iterable[str]) -> str:
    pins = tuple(sorted(pulse_pins))
    suffix = "STATIC" if not pins else "_".join(_sanitize(pin) for pin in pins) + "_P"
    name = f"{_sanitize(wft, 'WFT')}_{suffix}"
    meta = (wft, pins)
    if name in model.timeset_meta and model.timeset_meta[name] != meta:
        raise ConversionError(f"generated timeset name collision: {name}")
    model.timeset_meta[name] = meta
    return name


def _map_vector(model: Model, state: dict[str, str]) -> tuple[str, list[str]]:
    pulse_pins = [pin for pin in model.pins if state[pin] == "P"]
    values: list[str] = []
    for pin in model.pins:
        symbol = state[pin]
        if symbol == "P":
            mode = model.pulse_edges.get(pin, (None, 0, 0))[0]
            if mode == "ReturnToLow":
                symbol = "1"
            elif mode == "ReturnToHigh":
                symbol = "0"
            else:
                raise ConversionError(f"pin {pin!r} uses P without a supported waveform")
        elif symbol in "ZN":
            symbol = "X"
        elif symbol == "T":
            raise ConversionError("STIL compare symbol T is not supported")
        elif symbol not in "01HLX":
            raise ConversionError(f"unsupported vector symbol {symbol!r} on {pin!r}")
        values.append(symbol)
    return _timeset_name(model, state["__wft__"], pulse_pins), values


def _emit_vector(model: Model, state: dict[str, str]) -> None:
    timeset, values = _map_vector(model, state)
    model.ops.append(VectorOp(timeset, values))


def _execute_shift(
    model: Model,
    events: list[DefinitionEvent],
    state: dict[str, str],
    params: dict[str, str],
) -> None:
    vector_assignments: dict[str, str] | None = None
    for event in events:
        if event.kind == "W":
            state["__wft__"] = str(event.payload)
        elif event.kind == "C":
            _apply(model, state, event.payload, params)  # type: ignore[arg-type]
        elif event.kind == "V":
            if vector_assignments is not None:
                raise ConversionError("only one V statement is supported inside Shift")
            vector_assignments = event.payload  # type: ignore[assignment]
        else:
            raise ConversionError("nested Shift blocks are not supported")
    if vector_assignments is None:
        raise ConversionError("Shift contains no vector")

    scan_pins = {model.scan_in, model.scan_out}
    for target, template in vector_assignments.items():
        pins = _target_pins(model, target)
        if len(template) != len(pins):
            raise ConversionError(f"Shift assignment width mismatch for {target!r}")
        parameter = params.get(target)
        for index, (pin, symbol) in enumerate(zip(pins, template)):
            if symbol == "#" and pin in scan_pins:
                continue
            if symbol == "#":
                if parameter is not None and len(parameter) == len(pins):
                    symbol = parameter[index]
                elif pin in params and len(params[pin]) == 1:
                    symbol = params[pin]
                else:
                    symbol = state[pin]
            state[pin] = symbol

    scan_in = params.get(model.scan_in, state[model.scan_in] * model.scan_length)
    scan_out = params.get(model.scan_out, state[model.scan_out] * model.scan_length)
    if len(scan_in) != model.scan_length or len(scan_out) != model.scan_length:
        raise ConversionError(
            f"scan strings must both contain {model.scan_length} symbols "
            f"({model.scan_in}={len(scan_in)}, {model.scan_out}={len(scan_out)})"
        )
    if set(scan_in) - set("01"):
        raise ConversionError(f"unsupported scan-in symbols: {sorted(set(scan_in) - set('01'))}")
    if set(scan_out) - set("HLX"):
        raise ConversionError(f"unsupported scan-out symbols: {sorted(set(scan_out) - set('HLX'))}")

    timeset, values = _map_vector(model, state)
    values[model.pins.index(model.scan_in)] = "_"
    values[model.pins.index(model.scan_out)] = "_"
    model.ops.append(
        ScanOp(
            timeset,
            model.scan_length,
            values,
            {model.scan_in: scan_in, model.scan_out: scan_out},
        )
    )
    state[model.scan_in] = scan_in[-1]


def _execute_definition(
    model: Model,
    events: list[DefinitionEvent],
    state: dict[str, str],
    params: dict[str, str] | None = None,
) -> None:
    params = params or {}
    for event in events:
        if event.kind == "W":
            state["__wft__"] = str(event.payload)
        elif event.kind in {"C", "V"}:
            _apply(model, state, event.payload, params)  # type: ignore[arg-type]
            if event.kind == "V":
                _emit_vector(model, state)
        elif event.kind == "Shift":
            _execute_shift(model, event.payload, state, params)  # type: ignore[arg-type]


def _parse_pattern(text: str, model: Model, keep_labels: bool) -> None:
    match = re.search(r'^Pattern\s+"([^"]+)"\s*\{', text, re.MULTILINE)
    if not match:
        raise ConversionError("no top-level Pattern block found")
    model.pattern_name = _sanitize(match.group(1), "converted_pattern")
    open_pos = text.find("{", match.start(), match.end())
    body = text[open_pos + 1 : _balanced_end(text, open_pos)]
    state = {pin: "X" for pin in model.pins}
    state["__wft__"] = model.waveform_tables[0]

    pos = 0
    token_re = re.compile(r"\b(W|C|V|Macro|Call)\b")
    labels: set[str] = set()
    while token := token_re.search(body, pos):
        kind = token.group(1)
        if kind == "W":
            statement = re.match(r'W\s+"([^"]+)"\s*;', body[token.start() :])
            if not statement:
                raise ConversionError("malformed W statement in Pattern")
            state["__wft__"] = statement.group(1)
            pos = token.start() + statement.end()
            continue
        if kind in {"C", "V"}:
            open_block = body.find("{", token.end())
            end = _balanced_end(body, open_block)
            _apply(model, state, _assignments(body[open_block + 1 : end]))
            if kind == "V":
                _emit_vector(model, state)
            pos = end + 1
            continue
        if kind == "Macro":
            statement = re.match(r'Macro\s+"([^"]+)"\s*;', body[token.start() :])
            if not statement:
                raise ConversionError("malformed Macro statement")
            name = statement.group(1)
            if name not in model.macros:
                raise ConversionError(f"undefined macro {name!r}")
            _execute_definition(model, model.macros[name], state)
            pos = token.start() + statement.end()
            continue

        statement = re.match(r'Call\s+"([^"]+)"\s*\{', body[token.start() :])
        if not statement:
            raise ConversionError("malformed Call statement")
        name = statement.group(1)
        if name not in model.procedures:
            raise ConversionError(f"undefined procedure {name!r}")
        call_open = body.find("{", token.start(), token.start() + statement.end())
        call_end = _balanced_end(body, call_open)
        params = _assignments(body[call_open + 1 : call_end])
        before = len(model.ops)
        _execute_definition(model, model.procedures[name], state, params)

        if keep_labels and len(model.ops) > before:
            line_start = body.rfind("\n", pos, token.start()) + 1
            prefix = body[line_start : token.start()]
            label_match = re.search(r'"([^"]+)"\s*:\s*$', prefix)
            if label_match:
                label = _sanitize(label_match.group(1))
                base = label
                suffix = 2
                while label in labels:
                    label = f"{base}_{suffix}"
                    suffix += 1
                labels.add(label)
                model.ops[before].label = label
        pos = call_end + 1

    summary = re.search(
        r"Patterns reference\s+(\d+)\s+V statements, generating\s+(\d+)\s+test cycles", text
    )
    if summary:
        model.expected_v_statements = int(summary.group(1))
        model.expected_cycles = int(summary.group(2))


def _finish_with_halt(model: Model) -> None:
    if not model.ops:
        raise ConversionError("pattern generated no operations")
    last = model.ops[-1]
    if isinstance(last, VectorOp):
        last.opcode = "halt"
        return
    if last.count < 2:
        raise ConversionError("cannot split final one-cycle scan into scan plus halt")
    sequences = last.sequences.copy()
    last.count -= 1
    last.sequences = {pin: value[:-1] for pin, value in sequences.items()}
    values = last.base_values[:]
    for pin, sequence in sequences.items():
        values[model.pins.index(pin)] = sequence[-1]
    model.ops.append(VectorOp(last.timeset, values, opcode="halt"))


def _collect_timesets(model: Model) -> None:
    seen: set[str] = set()
    for op in model.ops:
        if op.timeset not in seen:
            model.used_timesets.append(op.timeset)
            seen.add(op.timeset)


def _write_pattern(model: Model, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("// Generated by stil-to-ni-digital.\n")
        out.write("file_format_version 1.1;\n")
        out.write(f"timeset {', '.join(model.used_timesets)};\n")
        out.write(f"scan_in {model.scan_in};\nscan_out {model.scan_out};\n\n")
        out.write(f"pattern {model.pattern_name} ({', '.join(model.pins)})\n{{\n")
        for op in model.ops:
            if op.label:
                out.write(f"{op.label}:\n")
            if isinstance(op, VectorOp):
                prefix = f"{op.opcode} " if op.opcode else ""
                out.write(f"{prefix}{op.timeset} {' '.join(op.values)};\n")
            else:
                out.write(f"scan({op.count}) {op.timeset} {' '.join(op.base_values)};\n{{\n")
                for pin in (model.scan_in, model.scan_out):
                    out.write(f"  {pin} {op.sequences[pin]};\n")
                out.write("};\n")
        out.write("}\n")


def _write_expanded_pattern(model: Model, path: Path) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n", buffering=1024 * 1024) as out:
        out.write("// Generated by stil-to-ni-digital; one vector per test cycle.\n")
        out.write("file_format_version 1.1;\n")
        out.write(f"timeset {', '.join(model.used_timesets)};\n\n")
        out.write(f"pattern {model.pattern_name}_expanded ({', '.join(model.pins)})\n{{\n")
        chunk: list[str] = []
        for op in model.ops:
            if op.label:
                chunk.append(f"{op.label}:\n")
            if isinstance(op, VectorOp):
                prefix = f"{op.opcode} " if op.opcode else ""
                chunk.append(f"{prefix}{op.timeset} {' '.join(op.values)};\n")
                count += 1
            else:
                indexes = [(model.pins.index(pin), sequence) for pin, sequence in op.sequences.items()]
                for index in range(op.count):
                    values = op.base_values[:]
                    for pin_index, sequence in indexes:
                        values[pin_index] = sequence[index]
                    chunk.append(f"{op.timeset} {' '.join(values)};\n")
                    count += 1
                    if len(chunk) >= 10000:
                        out.writelines(chunk)
                        chunk.clear()
            if len(chunk) >= 10000:
                out.writelines(chunk)
                chunk.clear()
        if chunk:
            out.writelines(chunk)
        out.write("}\n")
    return count


def _pin_edge(pin: str, period: float, compare: float, pulse: tuple[str, float, float] | None) -> str:
    lines = [f'          <PinEdge pin="{escape(pin)}">']
    if pulse:
        mode, data, ret = pulse
        lines += [
            f"            <{mode}>", "              <On>0 ns</On>",
            f"              <Data>{_fmt_ns(data)}</Data>",
            f"              <Return>{_fmt_ns(ret)}</Return>",
            f"              <Off>{_fmt_ns(period)}</Off>", f"            </{mode}>",
        ]
    else:
        lines += [
            "            <DriveNonReturn>", "              <On>0 ns</On>",
            "              <Data>0 ns</Data>", f"              <Off>{_fmt_ns(period)}</Off>",
            "            </DriveNonReturn>",
        ]
    lines += [
        "            <CompareStrobe>", f"              <Strobe>{_fmt_ns(compare)}</Strobe>",
        "            </CompareStrobe>", "            <DataSource>Pattern</DataSource>",
        "          </PinEdge>",
    ]
    return "\n".join(lines)


def _write_timing(model: Model, path: Path) -> None:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<TimingFile xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="1.0" '
        'xmlns="http://www.ni.com/Semiconductor/Timing">',
        "  <TimingSheet>",
        "    <Comment>Generated from STIL; P waveforms use dedicated NI timesets.</Comment>",
        "    <TimeSets>",
    ]
    for timeset in model.used_timesets:
        wft, pulse_pins = model.timeset_meta[timeset]
        period = model.periods_ns[wft]
        lines += [f'      <TimeSet name="{escape(timeset)}">', f"        <Period>{_fmt_ns(period)}</Period>", "        <PinEdges>"]
        for pin in model.pins:
            lines.append(_pin_edge(pin, period, model.compare_ns, model.pulse_edges.get(pin) if pin in pulse_pins else None))
        lines += ["        </PinEdges>", "      </TimeSet>"]
    lines += ["    </TimeSets>", "  </TimingSheet>", "</TimingFile>", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_pinmap(model: Model, path: Path) -> None:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<PinMap schemaVersion="1.5" xmlns="http://www.ni.com/TestStand/SemiconductorModule/PinMap.xsd" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">', "  <Pins>",
    ]
    lines += [f'    <DUTPin name="{escape(pin)}" />' for pin in model.pins]
    lines += ["  </Pins>", "  <PinGroups>", '    <PinGroup name="AllPins">']
    lines += [f'      <PinReference pin="{escape(pin)}" />' for pin in model.pins]
    lines += ["    </PinGroup>", "  </PinGroups>", "</PinMap>", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_report(model: Model, files: dict[str, Path], path: Path) -> None:
    cycles = sum(op.cycles for op in model.ops)
    lines = [
        "STIL to NI-Digital conversion report", "====================================", "",
        f"Source: {model.source}", f"Source SHA-256: {_sha256(model.source)}", "",
        f"Pins: {', '.join(f'{pin} ({model.directions[pin]})' for pin in model.pins)}",
        f"Waveform tables: {', '.join(model.waveform_tables)}",
        f"Scan chain: {model.scan_in} -> {model.scan_out}, length {model.scan_length}",
        f"Generated test cycles: {cycles}",
        f"Source-reported test cycles: {model.expected_cycles}",
        f"NI vector instructions: {sum(isinstance(op, VectorOp) for op in model.ops)}",
        f"NI scan instructions: {sum(isinstance(op, ScanOp) for op in model.ops)}", "",
        "Station configuration required:",
        "- The pin map is logical-only; add NI instruments, sites, channels, and connections.",
        "- STIL does not define NI voltage levels; provide .digilevels or API configuration.", "",
        "Files:",
    ]
    for kind, file_path in files.items():
        if kind != "report" and file_path.exists():
            lines.append(f"- {kind}: {file_path.name} ({file_path.stat().st_size} bytes, SHA-256 {_sha256(file_path)})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def convert_file(
    source: Path,
    output_dir: Path,
    *,
    expand_scan: bool = False,
    keep_labels: bool = True,
) -> ConversionResult:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not source.is_file():
        raise ConversionError(f"input file does not exist: {source}")
    text = _read_text(source)
    model = Model(source, output_dir)
    _parse_signals_groups(text, model)
    _parse_timing(text, model)
    _parse_scan(text, model)
    _parse_definitions(text, model)
    _parse_pattern(text, model, keep_labels)

    cycles = sum(op.cycles for op in model.ops)
    if model.expected_cycles is not None and cycles != model.expected_cycles:
        raise ConversionError(
            f"generated cycle count {cycles} differs from STIL summary {model.expected_cycles}"
        )
    _finish_with_halt(model)
    if sum(op.cycles for op in model.ops) != cycles:
        raise AssertionError("halt conversion changed the cycle count")
    _collect_timesets(model)

    output_dir.mkdir(parents=True, exist_ok=True)
    base = _output_base(source)
    files = {
        "pattern_source": output_dir / f"{base}.digipatsrc",
        "timing": output_dir / f"{base}.digitiming",
        "pinmap": output_dir / f"{base}.pinmap",
        "report": output_dir / "conversion_report.txt",
    }
    _write_pattern(model, files["pattern_source"])
    _write_timing(model, files["timing"])
    _write_pinmap(model, files["pinmap"])
    if expand_scan:
        expanded = output_dir / f"{base}.expanded.digipatsrc"
        expanded_count = _write_expanded_pattern(model, expanded)
        if expanded_count != cycles:
            raise AssertionError("expanded vector count differs from the STIL cycle count")
        files["expanded_pattern_source"] = expanded
    _write_report(model, files, files["report"])

    return ConversionResult(
        files=files,
        pins=tuple(model.pins),
        cycles=cycles,
        vector_instructions=sum(isinstance(op, VectorOp) for op in model.ops),
        scan_instructions=sum(isinstance(op, ScanOp) for op in model.ops),
    )
