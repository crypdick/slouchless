from __future__ import annotations

from pathlib import Path


def _is_docstring_start(line: str) -> bool:
    s = line.lstrip()
    return s.startswith('"""') or s.startswith("'''")


def _docstring_end_idx(lines: list[str], start_idx: int) -> int | None:
    """
    If `lines[start_idx]` begins a triple-quoted string, return the line index
    of the line *after* the closing delimiter. Otherwise return None.
    """
    first = lines[start_idx]
    s = first.lstrip()
    if s.startswith('"""'):
        delim = '"""'
    elif s.startswith("'''"):
        delim = "'''"
    else:
        return None

    # Single-line docstring: opening and closing on same line.
    if s.count(delim) >= 2:
        return start_idx + 1

    for i in range(start_idx + 1, len(lines)):
        if delim in lines[i]:
            return i + 1
    return None


def _find_insertion_point(lines: list[str]) -> int:
    """
    Return the line index where `from __future__ import annotations` should live:
    after shebang/encoding and after an optional module docstring.
    """
    i = 0
    # shebang
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    # encoding cookie (PEP 263) can be on 1st or 2nd line (after shebang)
    if i < len(lines) and "coding" in lines[i] and lines[i].lstrip().startswith("#"):
        i += 1
    # blank lines after shebang/encoding
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    # optional module docstring
    if i < len(lines) and _is_docstring_start(lines[i]):
        end = _docstring_end_idx(lines, i)
        if end is not None:
            i = end
        # keep trailing blank line(s) after docstring
        while i < len(lines) and lines[i].strip() == "":
            i += 1
    return i


def _normalize_newlines(text: str) -> tuple[str, str]:
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), nl


def _fix_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    text, nl = _normalize_newlines(raw)
    lines = text.splitlines(True)  # keep ends

    target = "from __future__ import annotations\n"

    # Find existing import line (exact match ignoring leading/trailing whitespace)
    existing_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "from __future__ import annotations":
            existing_idx = i
            break
    if existing_idx is None:
        return False

    # Remove the existing line plus a single following blank line (common style)
    lines.pop(existing_idx)
    if existing_idx < len(lines) and lines[existing_idx].strip() == "":
        lines.pop(existing_idx)

    insert_at = _find_insertion_point(lines)
    # Ensure there's exactly one blank line after future import.
    to_insert = [target, "\n"]
    lines[insert_at:insert_at] = to_insert

    new = "".join(lines).replace("\n", nl)
    if new == raw:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    repo_root = Path.cwd()

    changed: list[Path] = []
    for p in repo_root.rglob("*.py"):
        rel_parts = p.relative_to(repo_root).parts
        if any(part in {".git", ".venv", "__pycache__", ".cfg"} for part in rel_parts):
            continue
        if p.is_symlink():
            continue
        try:
            if _fix_file(p):
                changed.append(p)
        except Exception as e:
            print(f"[fix_future_annotations] error: {p}: {e}")
            return 2

    if changed:
        print("[fix_future_annotations] updated files:")
        for p in changed:
            print(f"- {p}")
        # Non-zero so pre-commit stops and user can re-run / re-stage.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
