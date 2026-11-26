"""Conversion between card references (backslash paths) and file system paths."""

from __future__ import annotations

from pathlib import Path

INVALID_NAME_CHARS = set('<>:"/\\|?*')


def split_reference(ref: str) -> list[str]:
    return [part for part in ref.replace("/", "\\").split("\\") if part]


def join_reference(*parts: str) -> str:
    return "\\".join(p for p in parts if p)


def resolve_case_insensitive(base: Path, parts: list[str]) -> Path | None:
    """Walk from base through parts, matching each component case-insensitively."""
    current = base
    for part in parts:
        if part == ".":
            continue
        candidate = current / part
        if candidate.exists():
            current = candidate
            continue
        if not current.is_dir():
            return None
        wanted = part.casefold()
        match = next((p for p in current.iterdir() if p.name.casefold() == wanted), None)
        if match is None:
            return None
        current = match
    return current


def resolve_sample_reference(card_root: Path, ref: str, owner_dir: Path) -> Path | None:
    """Resolve a samasst filename to a file system path.

    owner_dir is the folder of the XML file containing the reference. References
    starting with '.' and bare file names are relative to it, all others are
    relative to the card root.
    """
    if not ref:
        return None
    normalized = ref.replace("/", "\\")
    if normalized.startswith(".\\") or "\\" not in normalized:
        return resolve_case_insensitive(owner_dir, split_reference(normalized))
    return resolve_case_insensitive(card_root, split_reference(normalized))


def card_reference(card_root: Path, path: Path) -> str:
    return join_reference(*path.relative_to(card_root).parts)


def validate_name(name: str, max_length: int = 32) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a patch or file name on FAT32/exFAT."""
    errors: list[str] = []
    warnings: list[str] = []
    if not name.strip():
        errors.append("name is empty")
        return errors, warnings
    bad = sorted({c for c in name if c in INVALID_NAME_CHARS or ord(c) < 32})
    if bad:
        errors.append("name contains invalid characters: " + " ".join(repr(c) for c in bad))
    if name != name.rstrip(" ."):
        errors.append("name must not end with a space or dot")
    if not name.isascii():
        warnings.append("name contains non-ASCII characters, display on the device is unverified")
    if len(name) > max_length:
        warnings.append(f"name is longer than {max_length} characters, display on the device is unverified")
    return errors, warnings
