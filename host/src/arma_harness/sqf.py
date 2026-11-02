"""Host-side SQF handling: preprocessing for `compile` (which rejects comments and directives) and
a scan for load-time side effects before hot reloading a file."""
from __future__ import annotations

import re
from pathlib import Path


def strip_comments(src: str) -> str:
    """Remove // and /* */ comments outside string literals, keeping line numbers."""
    out: list[str] = []
    i, n, quote = 0, len(src), None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == quote:
                if i + 1 < n and src[i + 1] == quote:  # doubled quote = escaped quote
                    out.append(src[i + 1])
                    i += 1
                else:
                    quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            stop = end if end != -1 else n
            out.append("\n" * src.count("\n", i, stop))
            i = stop + 2 if end != -1 else n
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


_INCLUDE = re.compile(r'^\s*#include\s+["<](.+?)[">]\s*$', re.M)
_DIRECTIVE = re.compile(r"^\s*#(?!include\b)(\w+)", re.M)


class PreprocessError(ValueError):
    pass


def preprocess(path: Path, root: Path | None = None, _depth: int = 0) -> str:
    """Minimal preprocessor: comments and #include (relative to the file, or to ``root`` for
    mission-absolute paths). Other directives (#define, #ifdef...) are refused rather than
    silently mishandled."""
    if _depth > 16:
        raise PreprocessError("#include nesting too deep")
    src = strip_comments(path.read_text(encoding="utf-8-sig"))
    m = _DIRECTIVE.search(src)
    if m:
        raise PreprocessError(f"{path.name}: unsupported directive #{m.group(1)} (only #include)")

    def include(match: re.Match) -> str:
        rel = match.group(1).replace("\\", "/")
        target = (root / rel.lstrip("/")) if rel.startswith("/") and root else path.parent / rel
        if not target.exists() and root:
            target = root / rel
        return preprocess(target, root, _depth + 1)

    return _INCLUDE.sub(include, src)


_TOP_ASSIGN_CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*(compileFinal\s*)?\{")


def top_level_statements(src: str) -> list[str]:
    """Split comment-free SQF into top-level statements (outside any brackets/strings)."""
    stmts, buf, depth, quote = [], [], 0, None
    for c in src:
        buf.append(c)
        if quote:
            if c == quote:
                quote = None
            continue
        if c in "\"'":
            quote = c
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c == ";" and depth == 0:
            s = "".join(buf).strip()
            if s.strip(";").strip():
                stmts.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def side_effects(src: str) -> list[str]:
    """Top-level statements that are not `NAME = {code}` definitions: reloading re-runs them."""
    return [s[:120] for s in top_level_statements(src) if not _TOP_ASSIGN_CODE.match(s)]
