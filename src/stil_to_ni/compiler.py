"""Optional integration with the proprietary NI Digital Pattern Compiler."""

from __future__ import annotations

import shutil
import subprocess
import hashlib
import json
import re
from pathlib import Path
from .progress import Progress, ProgressCallback


COMMON_COMPILER_PATHS = (
    Path(r"C:\Program Files\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"),
    Path(r"C:\Program Files (x86)\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"),
)


def find_compiler(explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"NI Digital Pattern Compiler not found: {path}")
        return path

    command = shutil.which("DigitalPatternCompiler.exe") or shutil.which("DigitalPatternCompiler")
    if command:
        return Path(command).resolve()
    for candidate in COMMON_COMPILER_PATHS:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "NI Digital Pattern Compiler was not found. Install NI Digital Pattern Editor/Compiler "
        "or pass --compiler PATH."
    )


def compile_pattern(
    source: Path,
    pinmap: Path,
    output: Path,
    compiler: Path | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    report_progress = Progress(progress)
    report_progress(0, 'NI 编译中（编译器不提供内部百分比）')
    executable = find_compiler(compiler)
    command = [str(executable), "-pinmap", str(pinmap), "-o", str(output), str(source)]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    log = {'compiler': str(executable), 'command': command, 'exit_code': result.returncode,
           'stdout': result.stdout, 'stderr': result.stderr,
           'compile_ok': result.returncode == 0, 'readback_ok': False}
    log_path = output.with_suffix('.compile.json')
    if result.returncode != 0:
        _save_validation(source, output, log_path, log)
        detail = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        raise RuntimeError(f"NI compiler failed with exit code {result.returncode}:\n{detail}")
    readback = output.with_suffix('.readback.digipatsrc')
    report_progress(40, 'NI 反编译校验中')
    reverse_command = [str(executable), '-decompile', '-o', str(readback), str(output)]
    reverse = subprocess.run(reverse_command, text=True, capture_output=True, check=False)
    log['readback'] = {'command': reverse_command, 'exit_code': reverse.returncode,
                       'stdout': reverse.stdout, 'stderr': reverse.stderr}
    if reverse.returncode == 0:
        report_progress(70, '核对源文件和反编译结果')
        log['source_semantic_hash'] = _normalized_digest(source)
        log['readback_semantic_hash'] = _normalized_digest(readback)
        log['readback_ok'] = log['source_semantic_hash'] == log['readback_semantic_hash']
    _save_validation(source, output, log_path, log)
    if not log['readback_ok']:
        raise RuntimeError(f'NI round-trip verification failed; see {log_path}')
    report_progress(100, '编译和校验完成')
    return result


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_digest(path: Path) -> str:
    """Ignore whitespace/comments and timeset declaration order only."""
    digest = hashlib.sha256()
    with path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            code = line.split('//', 1)[0].strip()
            if code.startswith('timeset '):
                code = 'timeset ' + ','.join(sorted(item.strip() for item in code[8:].rstrip(';').split(','))) + ';'
            digest.update(re.sub(r'\s+', '', code).encode())
    return digest.hexdigest()


def _save_validation(source: Path, output: Path, log_path: Path, log: dict) -> None:
    log['source_sha256'] = _file_hash(source)
    if output.exists():
        log['binary_sha256'] = _file_hash(output)
        log['binary_bytes'] = output.stat().st_size
    log_path.write_text(json.dumps(log, indent=2) + '\n', encoding='utf-8')
    manifest_path = source.parent / 'build_manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        records = manifest.setdefault('compilation', {})
        records[source.name] = {'compile_ok': log['compile_ok'], 'readback_ok': log['readback_ok'],
                                'log': log_path.name, 'log_sha256': _file_hash(log_path),
                                'binary_sha256': log.get('binary_sha256')}
        expected = [record['path'] for record in manifest['files'].values() if record['path'].endswith('.digipatsrc')]
        for flag in ('compile_ok', 'readback_ok'):
            manifest['validation'][flag] = all(records.get(name, {}).get(flag) is True for name in expected)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
