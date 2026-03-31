"""Normalize state court opinion datasets into a standard directory structure.

Architecture:
  - This file: shared infrastructure (StateConfig, helpers, CLI entry point)
  - handlers_existing.py: organiser functions for the 9 original states
  - handlers_new.py: organiser functions for the 9 new states

Directory layout:
  RAW_ROOT   = LegalAI-Scraper/<state>/           (CSVs + raw PDFs)
  TXT_ROOT   = LegalAI-Scraper/txt_output/<state>/ (converted .txt files)
  OUTPUT_ROOT = clean-data/                         (organised output)
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Path roots
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent           # LegalAI-Scraper/
RAW_ROOT = PROJECT_ROOT                            # CSVs + PDFs live here
TXT_ROOT = PROJECT_ROOT / "txt_output"             # converted .txt files
OUTPUT_ROOT = SCRIPT_DIR                           # clean-data/ (organised output)
PHASE2_ROOT = PROJECT_ROOT.parent / "Source Code Legal AI"  # Phase 2 raw data


# ---------------------------------------------------------------------------
# Metadata schema
# ---------------------------------------------------------------------------
STANDARD_FIELDS = [
    "state",
    "court_name",
    "court_folder",
    "year",
    "case_id",
    "case_folder",
    "case_title",
    "opinion_date",
    "source_text_path",
    "output_case_path",
]


@dataclass
class CaseEntry:
    state: str
    court_name: str
    court_folder: str
    year: str
    case_id: str
    case_folder: str
    case_title: str
    opinion_date: str
    source_text_path: str
    output_case_path: str
    raw: dict[str, str]


@dataclass
class StateConfig:
    """Holds the three root directories for a single state."""
    raw_root: Path     # LegalAI-Scraper/<state>/  — CSVs + raw PDFs
    txt_root: Path     # LegalAI-Scraper/txt_output/<state>/ — converted .txt
    output_root: Path  # clean-data/<state>/ — organised output


def make_state_config(state_key: str) -> StateConfig:
    return StateConfig(
        raw_root=RAW_ROOT / state_key,
        txt_root=TXT_ROOT / state_key,
        output_root=OUTPUT_ROOT / state_key,
    )


def make_phase2_config(state_key: str, source_dir_name: str) -> StateConfig:
    """Create config for Phase 2 states (Source Code Legal AI)."""
    return StateConfig(
        raw_root=PHASE2_ROOT / source_dir_name,
        txt_root=TXT_ROOT / state_key,
        output_root=OUTPUT_ROOT / state_key,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def sanitize_case_component(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "case"


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        # Remove contents but keep the directory if rmtree fails (WSL permission issue)
        try:
            shutil.rmtree(path)
        except PermissionError:
            # Try to remove contents individually instead
            for child in path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
    path.mkdir(parents=True, exist_ok=True)


def parse_date(value: str, formats: list[str]) -> datetime | None:
    value = (value or "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def year_from_value(value: str, formats: list[str]) -> str:
    parsed = parse_date(value, formats)
    if parsed:
        return parsed.strftime("%Y")
    match = re.search(r"(?:19|20)\d{2}", value or "")
    return match.group(0) if match else "unknown_year"


def make_unique_case_folder(base_name: str, opinion_date: str, used: set[str]) -> str:
    # Use lowercase for comparison to avoid collisions on case-insensitive filesystems (NTFS)
    check_name = base_name.lower()
    if check_name not in used:
        used.add(check_name)
        return base_name

    suffix = ""
    parsed = parse_date(opinion_date, ["%m/%d/%y", "%B %d, %Y", "%b %d, %Y",
                                        "%Y-%m-%d", "%m/%d/%Y"])
    if parsed:
        suffix = parsed.strftime("%Y_%m_%d")

    candidate = f"{base_name}__{suffix}" if suffix else f"{base_name}__2"
    if candidate.lower() not in used:
        used.add(candidate.lower())
        return candidate

    index = 2
    while True:
        candidate = f"{base_name}__{suffix}_{index}" if suffix else f"{base_name}__{index}"
        if candidate.lower() not in used:
            used.add(candidate.lower())
            return candidate
        index += 1


def write_metadata(court_dir: Path, court_folder: str, entries: list[CaseEntry]) -> None:
    raw_fields = sorted({key for entry in entries for key in entry.raw
                         if key not in STANDARD_FIELDS})
    fieldnames = STANDARD_FIELDS + raw_fields
    metadata_path = court_dir / f"{court_folder}_metadata.csv"

    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in sorted(entries, key=lambda item: (item.year, item.case_folder)):
            row = {field: getattr(entry, field) for field in STANDARD_FIELDS}
            row.update({field: entry.raw.get(field, "") for field in raw_fields})
            writer.writerow(row)


def build_text_index_by_basename(root: Path) -> dict[str, Path]:
    """Index all .txt files under *root* by lowercased stem."""
    index: dict[str, Path] = {}
    for path in root.rglob("*.txt"):
        index[path.stem.lower()] = path
    return index


def build_colorado_index(text_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in text_dir.glob("*.txt"):
        match = re.match(r"translation-(\d+)_", path.stem, flags=re.I)
        if match:
            index[match.group(1)] = path
    return index


def colorado_translation_id(row: dict[str, str]) -> str:
    for key in ("detail_url", "pdf_url"):
        value = row.get(key, "")
        match = re.search(r"/(?:vid|pdf)/(\d+)", value)
        if match:
            return match.group(1)
    return ""


def relative_str(path: Path, start: Path) -> str:
    """Return *path* relative to *start* as a string (forward slashes)."""
    try:
        return str(path.relative_to(start))
    except ValueError:
        return str(path)


def first_regex_match(value: str, pattern: str) -> str:
    match = re.search(pattern, value or "")
    return match.group(1) if match else ""


def text_path_from_flat_index(row: dict[str, str],
                              text_index: dict[str, Path]) -> Path | None:
    pdf_local_path = row.get("pdf_local_path", "")
    if pdf_local_path:
        # Normalize backslashes for cross-platform compatibility
        normalized = pdf_local_path.replace("\\", "/")
        text_path = text_index.get(Path(normalized).stem.lower())
        if text_path:
            return text_path

    for key in ("pdf_url", "case_pdf_url", "read_full_url"):
        value = row.get(key, "")
        if not value:
            continue
        stem = Path(value.split("?", 1)[0]).stem.lower()
        if stem in text_index:
            return text_index[stem]
    return None


def path_stem_from_row(row: dict[str, str]) -> str:
    pdf_local_path = row.get("pdf_local_path", "")
    if pdf_local_path:
        # Normalize backslashes for cross-platform compatibility
        return Path(pdf_local_path.replace("\\", "/")).stem.lower()

    for key in ("pdf_url", "case_pdf_url", "read_full_url"):
        value = row.get(key, "")
        if value:
            return Path(value.split("?", 1)[0]).stem.lower()
    return ""


def montana_text_year(text_path: Path) -> str:
    try:
        text = text_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    header = "\n".join(text.splitlines()[:10])
    match = re.search(r"\b((?:19|20)\d{2})\s+MT\s+\d+\b", header)
    return match.group(1) if match else ""


def normalize_nj_date(raw: str) -> str:
    """Normalise New Jersey date strings that may use abbreviations like
    ``Feb.``, ``Jan.``, ``Aug.``, as well as full month names."""
    raw = raw.strip().rstrip(".")
    # Remove trailing dots on abbreviated months
    raw = re.sub(r"(\b\w{3})\.", r"\1", raw)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        parsed = parse_date(raw, [fmt])
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    return raw


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
from typing import Callable

ReorgFunc = Callable[[StateConfig], dict[str, int]]


def _build_reorganizers() -> dict[str, ReorgFunc]:
    """Import handler modules and merge their REORGANIZERS dicts."""
    from handlers_existing import REORGANIZERS as existing
    from handlers_new import REORGANIZERS as new
    merged = {}
    merged.update(existing)
    merged.update(new)
    try:
        from handlers_phase2 import REORGANIZERS as phase2
        merged.update(phase2)
    except ImportError:
        pass
    return merged


def main() -> None:
    reorganizers = _build_reorganizers()

    # Phase 2 states need different source dirs
    try:
        from handlers_phase2 import PHASE2_SOURCE_DIRS
    except ImportError:
        PHASE2_SOURCE_DIRS = {}

    parser = argparse.ArgumentParser(
        description="Normalize state court opinion datasets.",
    )
    parser.add_argument(
        "states", nargs="*", choices=sorted(reorganizers),
        help="State folders to reorganise (default: all)",
    )
    args = parser.parse_args()

    states = args.states or sorted(reorganizers)
    for state in states:
        if state in PHASE2_SOURCE_DIRS:
            cfg = make_phase2_config(state, PHASE2_SOURCE_DIRS[state])
        else:
            cfg = make_state_config(state)
        counts = reorganizers[state](cfg)
        summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        print(f"{state}: {summary}")


if __name__ == "__main__":
    main()
