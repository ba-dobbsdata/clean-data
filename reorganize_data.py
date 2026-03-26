from __future__ import annotations

import csv
import hashlib
import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
PRIMARY_SOURCE_ROOT = ROOT / "downloads" / "court_opinions"
ARCHIVE_SOURCE_ROOT = ROOT / "archive" / "downloads" / "court_opinions"
STATE_NAME = "California"
STATE_SLUG = "california"


CASE_SUMMARY_FIELDS = {
    "case_caption": "Case Caption:",
    "case_type": "Case Type:",
    "filing_date": "Filing Date:",
    "completion_date": "Completion Date:",
    "oral_argument_datetime": "Oral Argument Date/Time:",
}

HTML_NAME_MAP = {
    "briefs": "briefs.html",
    "case_summary": "case_summary.html",
    "disposition": "disposition.html",
    "docket": "docket.html",
    "lower_court": "lower_court.html",
}


@dataclass
class CaseRecord:
    state: str
    court_name: str
    court_folder: str
    year: str
    case_id: str
    case_caption: str
    case_type: str
    filing_date: str
    completion_date: str
    oral_argument_datetime: str
    opinion_available: str
    opinion_file_status: str
    opinion_source_files: str
    extra_output_files: str
    source_case_path: str
    output_case_path: str


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalize_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_case_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {key: "" for key in CASE_SUMMARY_FIELDS}

    raw = read_text(path)
    parsed: dict[str, str] = {}
    for field, label in CASE_SUMMARY_FIELDS.items():
        pattern = (
            re.escape(f'<div class="col-5 col-md-3">{label}</div>')
            + r"\s*<div class=\"col-7 col-md-9\">(.*?)</div>"
        )
        match = re.search(pattern, raw, flags=re.S)
        parsed[field] = normalize_text(match.group(1)) if match else ""
    return parsed


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_opinion_files(txt_files: list[Path]) -> tuple[Path | None, list[Path], str]:
    if not txt_files:
        return None, [], "missing"

    hashed: dict[str, list[Path]] = {}
    for path in txt_files:
        hashed.setdefault(hash_file(path), []).append(path)

    distinct_groups = list(hashed.values())
    primary = max(
        (path for group in distinct_groups for path in group),
        key=lambda item: (item.stat().st_size, len(item.name), item.name),
    )
    primary_hash = hash_file(primary)

    alternates = [
        path
        for group in distinct_groups
        for path in group
        if path != primary and hash_file(path) != primary_hash
    ]

    if len(txt_files) == 1:
        status = "single_source"
    elif len(distinct_groups) == 1:
        status = "duplicate_identical_sources"
    else:
        status = "multiple_distinct_sources"

    return primary, alternates, status


def copy_html_files(case_dir: Path, dest_case_dir: Path) -> list[str]:
    extra_files: list[str] = []
    for source_file in sorted(case_dir.iterdir()):
        if not source_file.is_file() or source_file.suffix.lower() != ".html":
            continue

        target_name = source_file.name
        match = re.search(r"__(.+)\.html$", source_file.name, flags=re.I)
        if match:
            target_name = HTML_NAME_MAP.get(match.group(1).lower(), f"{slugify(match.group(1))}.html")
        else:
            target_name = f"{slugify(source_file.stem)}.html"

        shutil.copy2(source_file, dest_case_dir / target_name)
        extra_files.append(target_name)
    return extra_files


def resolve_source_root() -> Path:
    if PRIMARY_SOURCE_ROOT.exists():
        return PRIMARY_SOURCE_ROOT
    if ARCHIVE_SOURCE_ROOT.exists():
        return ARCHIVE_SOURCE_ROOT
    raise FileNotFoundError(f"Source root not found: {PRIMARY_SOURCE_ROOT} or {ARCHIVE_SOURCE_ROOT}")


def derive_year(summary: dict[str, str], opinion_text: str, fallback_year: str) -> str:
    header_window = "\n".join(opinion_text.splitlines()[:8]) if opinion_text else ""
    filed_match = re.search(r"\bFiled\s+(\d{1,2})/(\d{1,2})/(\d{2,4})\b", header_window, flags=re.I)
    if filed_match:
        raw_year = filed_match.group(3)
        if len(raw_year) == 2:
            raw_year = f"20{raw_year}"
        return raw_year

    completion_date = summary.get("completion_date", "")
    completion_match = re.search(r"(\d{4})$", completion_date)
    if completion_match:
        return completion_match.group(1)

    return fallback_year


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def iter_source_year_dirs(source_root: Path) -> Iterable[tuple[str, Path]]:
    for path in sorted(source_root.iterdir()):
        if not path.is_dir():
            continue
        match = re.fullmatch(r"search_backup_filtered_(\d{4})", path.name)
        if match:
            yield match.group(1), path


def reorganize() -> dict[str, int]:
    source_root = resolve_source_root()

    destination_state_dir = ROOT / STATE_SLUG
    destination_state_dir.mkdir(exist_ok=True)

    records_by_court: dict[str, list[CaseRecord]] = {}
    prepared_courts: set[str] = set()
    counters = {
        "courts": 0,
        "total_source_cases": 0,
        "cases_retained": 0,
        "skipped_missing_opinion_source": 0,
        "pdf_only_cases": 0,
        "duplicate_identical_sources": 0,
        "multiple_distinct_sources": 0,
    }

    for source_year, year_dir in iter_source_year_dirs(source_root):
        for court_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            court_name = court_dir.name
            court_slug = slugify(court_name)
            dest_court_dir = destination_state_dir / court_slug
            if court_slug not in prepared_courts:
                ensure_clean_dir(dest_court_dir)
                prepared_courts.add(court_slug)
                counters["courts"] += 1
            records = records_by_court.setdefault(court_slug, [])

            case_dirs = sorted(p for p in court_dir.iterdir() if p.is_dir())

            for case_dir in case_dirs:
                counters["total_source_cases"] += 1
                summary_path = case_dir / f"{case_dir.name}__case_summary.html"
                summary = parse_case_summary(summary_path)

                txt_files = sorted(case_dir.glob("*.txt"))
                pdf_files = sorted(case_dir.glob("*.pdf"))
                if not txt_files:
                    if pdf_files:
                        counters["pdf_only_cases"] += 1
                    else:
                        counters["skipped_missing_opinion_source"] += 1
                    continue

                primary_opinion, alternates, opinion_status = choose_opinion_files(txt_files)
                opinion_text = read_text(primary_opinion)
                case_year = derive_year(summary, opinion_text, source_year)
                dest_case_dir = dest_court_dir / case_year / case_dir.name
                ensure_clean_dir(dest_case_dir)
                extra_output_files = copy_html_files(case_dir, dest_case_dir)

                shutil.copy2(primary_opinion, dest_case_dir / "opinion.txt")
                opinion_available = "yes"

                for index, alternate in enumerate(alternates, start=1):
                    alt_name = f"opinion_alt_{index}.txt"
                    shutil.copy2(alternate, dest_case_dir / alt_name)
                    extra_output_files.append(alt_name)

                if opinion_status == "duplicate_identical_sources":
                    counters["duplicate_identical_sources"] += 1
                elif opinion_status == "multiple_distinct_sources":
                    counters["multiple_distinct_sources"] += 1

                records.append(
                    CaseRecord(
                        state=STATE_NAME,
                        court_name=court_name,
                        court_folder=court_slug,
                        year=case_year,
                        case_id=case_dir.name,
                        case_caption=summary.get("case_caption", ""),
                        case_type=summary.get("case_type", ""),
                        filing_date=summary.get("filing_date", ""),
                        completion_date=summary.get("completion_date", ""),
                        oral_argument_datetime=summary.get("oral_argument_datetime", ""),
                        opinion_available=opinion_available,
                        opinion_file_status=opinion_status,
                        opinion_source_files="; ".join(path.name for path in txt_files),
                        extra_output_files="; ".join(sorted(extra_output_files)),
                        source_case_path=str(case_dir.relative_to(ROOT)),
                        output_case_path=str(dest_case_dir.relative_to(ROOT)),
                    )
                )
                counters["cases_retained"] += 1

    for court_slug, records in records_by_court.items():
        metadata_path = destination_state_dir / court_slug / f"{court_slug}_metadata.csv"
        fieldnames = list(CaseRecord.__dataclass_fields__.keys())
        with metadata_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in sorted(records, key=lambda item: (item.year, item.case_id)):
                writer.writerow(record.__dict__)

    return counters


if __name__ == "__main__":
    counts = reorganize()
    for key, value in counts.items():
        print(f"{key}: {value}")
