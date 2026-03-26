from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent


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
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def parse_date(value: str, formats: list[str]) -> datetime | None:
    value = (value or "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def make_unique_case_folder(base_name: str, opinion_date: str, used: set[str]) -> str:
    if base_name not in used:
        used.add(base_name)
        return base_name

    suffix = ""
    parsed = parse_date(opinion_date, ["%m/%d/%y", "%B %d, %Y", "%b %d, %Y"])
    if parsed:
        suffix = parsed.strftime("%Y_%m_%d")

    candidate = f"{base_name}__{suffix}" if suffix else f"{base_name}__2"
    if candidate not in used:
        used.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = f"{base_name}__{suffix}_{index}" if suffix else f"{base_name}__{index}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def write_metadata(court_dir: Path, court_folder: str, entries: list[CaseEntry]) -> None:
    raw_fields = sorted({key for entry in entries for key in entry.raw if key not in STANDARD_FIELDS})
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
    return str(path.relative_to(start))


def first_regex_match(value: str, pattern: str) -> str:
    match = re.search(pattern, value or "")
    return match.group(1) if match else ""


def year_from_value(value: str, formats: list[str]) -> str:
    parsed = parse_date(value, formats)
    if parsed:
        return parsed.strftime("%Y")

    match = re.search(r"(19|20)\d{2}", value or "")
    return match.group(0) if match else ""


def text_path_from_flat_index(row: dict[str, str], text_index: dict[str, Path]) -> Path | None:
    pdf_local_path = row.get("pdf_local_path", "")
    if pdf_local_path:
        text_path = text_index.get(Path(pdf_local_path).stem.lower())
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
        return Path(pdf_local_path).stem.lower()

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
    if match:
        return match.group(1)
    return ""


def reorganize_florida(state_root: Path) -> dict[str, int]:
    state_name = "Florida"
    output_root = state_root / "florida"
    ensure_clean_dir(output_root)

    verify_downloads = ROOT / "verify-data" / "florida" / "downloads"
    use_verify = verify_downloads.exists()
    csv_root = verify_downloads if use_verify else (state_root / "downloads")
    text_dir = state_root / "download" / "verify_text" if use_verify else (state_root / "download" / "pdf")
    text_index = {path.stem.lower(): path for path in text_dir.glob("*.txt")} if not use_verify else {}
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    for court_dir in sorted(csv_root.iterdir()):
        if not court_dir.is_dir():
            continue
        csv_path = court_dir / "fl_opinions.csv"
        if not csv_path.exists():
            continue

        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            counts["rows_total"] += 1
            if use_verify:
                pdf_rel = Path(row["pdf_path"].replace("\\", "/"))
                pdf_parts = list(pdf_rel.parts)
                if pdf_parts and pdf_parts[0].lower() == "downloads":
                    pdf_rel = Path(*pdf_parts[1:])
                text_path = (text_dir / pdf_rel).with_suffix(".txt")
            else:
                text_key = Path(row["pdf_file"]).stem.lower()
                text_path = text_index.get(text_key)
            if not text_path:
                counts["rows_skipped_missing_text"] += 1
                continue
            if not text_path.exists():
                counts["rows_skipped_missing_text"] += 1
                continue

            court_code = (row.get("court") or court_dir.name).strip() or "unknown_court"
            court_folder = slugify(court_code)
            court_name = court_code
            opinion_dt = parse_date(row.get("release_date", ""), ["%m/%d/%y"])
            year = opinion_dt.strftime("%Y") if opinion_dt else row.get("release_date", "")[-2:]
            case_id = row.get("case_no", "").strip() or Path(row["pdf_file"]).stem
            base_folder = sanitize_case_component(case_id)
            case_folder = make_unique_case_folder(
                base_folder,
                row.get("release_date", ""),
                used_folders[(court_folder, year)],
            )

            dest_case_dir = output_root / court_folder / year / case_folder
            dest_case_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(text_path, dest_case_dir / "opinion.txt")

            court_entries[court_folder].append(
                CaseEntry(
                    state=state_name,
                    court_name=court_name,
                    court_folder=court_folder,
                    year=year,
                    case_id=case_id,
                    case_folder=case_folder,
                    case_title=row.get("case_name", "").strip(),
                    opinion_date=row.get("release_date", "").strip(),
                    source_text_path=relative_str(text_path, state_root),
                    output_case_path=relative_str(dest_case_dir, state_root),
                    raw=row,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


def reorganize_georgia(state_root: Path) -> dict[str, int]:
    state_name = "Georgia"
    output_root = state_root / "georgia"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "ga_supreme" / "CSV" / "ga_supreme_all_years.csv"
    text_index = build_text_index_by_basename(state_root / "download")
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    court_folder = "supreme_court"
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)
    entries: list[CaseEntry] = []

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_key = Path(row["pdf_file"]).stem.lower()
        text_path = text_index.get(text_key)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        opinion_date = row.get("date", "").strip()
        parsed_opinion_date = parse_date(opinion_date, ["%B %d, %Y"])
        year = parsed_opinion_date.strftime("%Y") if parsed_opinion_date else row.get("year", "").strip()
        case_id = row.get("case_id", "").strip()
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Georgia Supreme Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_title", "").strip(),
                opinion_date=opinion_date,
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


def reorganize_iowa(state_root: Path) -> dict[str, int]:
    state_name = "Iowa"
    output_root = state_root / "iowa"
    ensure_clean_dir(output_root)

    configs = [
        {
            "csv": state_root / "downloads" / "supreme-court" / "CSV" / "iowa_supreme_court_opinions.csv",
            "court_name": "Iowa Supreme Court",
            "court_folder": "supreme_court",
        },
        {
            "csv": state_root / "downloads" / "court-of-appeals" / "CSV" / "iowa_court_of_appeals_opinions.csv",
            "court_name": "Iowa Court of Appeals",
            "court_folder": "court_of_appeals",
        },
    ]

    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    for config in configs:
        with config["csv"].open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            counts["rows_total"] += 1
            pdf_local_path = Path(row["pdf_local_path"].replace("/", "\\"))
            text_path = state_root / pdf_local_path.with_suffix(".txt")
            if not text_path.exists():
                counts["rows_skipped_missing_text"] += 1
                continue

            opinion_date = row.get("filed_date", "").strip()
            parsed_opinion_date = parse_date(opinion_date, ["%b %d, %Y"])
            year = parsed_opinion_date.strftime("%Y") if parsed_opinion_date else pdf_local_path.parts[2]
            case_id = row.get("case_no", "").strip()
            case_folder = make_unique_case_folder(
                sanitize_case_component(case_id),
                opinion_date,
                used_folders[(config["court_folder"], year)],
            )

            dest_case_dir = output_root / config["court_folder"] / year / case_folder
            dest_case_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(text_path, dest_case_dir / "opinion.txt")

            court_entries[config["court_folder"]].append(
                CaseEntry(
                    state=state_name,
                    court_name=config["court_name"],
                    court_folder=config["court_folder"],
                    year=year,
                    case_id=case_id,
                    case_folder=case_folder,
                    case_title=row.get("case_caption", "").strip(),
                    opinion_date=opinion_date,
                    source_text_path=relative_str(text_path, state_root),
                    output_case_path=relative_str(dest_case_dir, state_root),
                    raw=row,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


def reorganize_colorado(state_root: Path) -> dict[str, int]:
    state_name = "Colorado"
    output_root = state_root / "colorado"
    ensure_clean_dir(output_root)

    configs = [
        {
            "csv": next((state_root / "downloads" / "colorado_supreme_court" / "CSV").glob("*.csv")),
            "text_dir": state_root / "download" / "colorado_supreme_court" / "pdf",
            "court_name": "Colorado Supreme Court",
            "court_folder": "supreme_court",
        },
        {
            "csv": next((state_root / "downloads" / "colorado_court_of_appeals" / "CSV").glob("*.csv")),
            "text_dir": state_root / "download" / "colorado_court_of_appeals" / "pdf",
            "court_name": "Colorado Court of Appeals",
            "court_folder": "court_of_appeals",
        },
    ]

    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    for config in configs:
        text_index = build_colorado_index(config["text_dir"])
        with config["csv"].open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            counts["rows_total"] += 1
            translation_id = colorado_translation_id(row)
            text_path = text_index.get(translation_id)
            if not text_path:
                counts["rows_skipped_missing_text"] += 1
                continue

            parsed = parse_date(row.get("date", ""), ["%B %d, %Y"])
            year = parsed.strftime("%Y") if parsed else ""
            case_id = row.get("docket_number", "").strip()
            case_folder = make_unique_case_folder(
                sanitize_case_component(case_id),
                row.get("date", ""),
                used_folders[(config["court_folder"], year)],
            )

            dest_case_dir = output_root / config["court_folder"] / year / case_folder
            dest_case_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(text_path, dest_case_dir / "opinion.txt")

            raw = dict(row)
            raw["translation_id"] = translation_id
            court_entries[config["court_folder"]].append(
                CaseEntry(
                    state=state_name,
                    court_name=config["court_name"],
                    court_folder=config["court_folder"],
                    year=year,
                    case_id=case_id,
                    case_folder=case_folder,
                    case_title=row.get("title", "").strip(),
                    opinion_date=row.get("date", "").strip(),
                    source_text_path=relative_str(text_path, state_root),
                    output_case_path=relative_str(dest_case_dir, state_root),
                    raw=raw,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


def reorganize_louisiana(state_root: Path) -> dict[str, int]:
    state_name = "Louisiana"
    output_root = state_root / "louisiana"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "Louisiana_Supreme_Court" / "CSV" / "lasc_cases.csv"
    text_index = build_text_index_by_basename(state_root / "downloads" / "PDF")
    court_folder = "supreme_court"
    counts = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "rows_skipped_duplicate_record": 0,
        "courts": 0,
    }
    entries: list[CaseEntry] = []
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)
    seen_records: set[tuple[str, str, str, str]] = set()

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_path = text_path_from_flat_index(row, text_index)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        opinion_date = row.get("published_date", "").strip()
        year = year_from_value(opinion_date, ["%Y-%m-%dT%H:%M:%S"])
        case_id = Path(text_path).stem
        record_key = (court_folder, year, case_id.lower(), text_path.name.lower())
        if record_key in seen_records:
            counts["rows_skipped_duplicate_record"] += 1
            continue
        seen_records.add(record_key)

        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )
        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        raw = dict(row)
        raw["matched_text_name"] = text_path.name
        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Louisiana Supreme Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("listing_title", "").strip(),
                opinion_date=opinion_date,
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=raw,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


def reorganize_maine(state_root: Path) -> dict[str, int]:
    state_name = "Maine"
    output_root = state_root / "maine"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "supreme_court" / "CSV" / "supreme_court.csv"
    text_index = build_text_index_by_basename(state_root / "downloads" / "PDF")
    court_folder = "supreme_court"
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    entries: list[CaseEntry] = []
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_path = text_path_from_flat_index(row, text_index)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        opinion_date = row.get("date_filed", "").strip()
        year = year_from_value(opinion_date, ["%B %d, %Y"])
        case_id = row.get("opinion_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Maine Supreme Judicial Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_name", "").strip(),
                opinion_date=opinion_date,
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


def maryland_court_config(case_pdf_url: str) -> tuple[str, str]:
    case_pdf_url = case_pdf_url or ""
    if "/coa/" in case_pdf_url:
        return ("supreme_court", "Maryland Supreme Court")
    return ("appellate_court", "Maryland Appellate Court")


def reorganize_maryland(state_root: Path) -> dict[str, int]:
    state_name = "Maryland"
    output_root = state_root / "maryland"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "appellate_court_opinions" / "CSV" / "cases.csv"
    text_index = build_text_index_by_basename(state_root / "downloads" / "PDF")
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_path = text_path_from_flat_index(row, text_index)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        court_folder, court_name = maryland_court_config(row.get("case_pdf_url", ""))
        opinion_date = first_regex_match(row.get("filed_date", ""), r"((?:19|20)\d{2}-\d{2}-\d{2})")
        year = year_from_value(opinion_date, ["%Y-%m-%d"])
        case_id = (row.get("docket_term", "").strip() or text_path.stem).replace("/", "-")
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        raw = dict(row)
        raw["matched_text_name"] = text_path.name
        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("parties", "").strip(),
                opinion_date=row.get("filed_date", "").strip(),
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=raw,
            )
        )
        counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


def reorganize_massachusetts(state_root: Path) -> dict[str, int]:
    state_name = "Massachusetts"
    output_root = state_root / "massachusetts"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "appeals_court" / "CSV" / "appeals_court_cases.csv"
    text_index = build_text_index_by_basename(state_root / "downloads" / "PDF")
    court_folder = "appeals_court"
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    entries: list[CaseEntry] = []
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_path = text_path_from_flat_index(row, text_index)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        opinion_date = row.get("release_date", "").strip()
        year = year_from_value(opinion_date, ["%Y-%m-%d"])
        case_id = row.get("docket_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Massachusetts Appeals Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_name", "").strip(),
                opinion_date=opinion_date,
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


def reorganize_montana(state_root: Path) -> dict[str, int]:
    state_name = "Montana"
    output_root = state_root / "montana"
    ensure_clean_dir(output_root)

    csv_path = state_root / "downloads" / "supreme_court" / "CSV" / "supreme_court_daily_orders.csv"
    text_index = build_text_index_by_basename(state_root / "downloads" / "PDF")
    court_folder = "supreme_court"
    counts = {"rows_total": 0, "cases_retained": 0, "rows_skipped_missing_text": 0, "courts": 0}
    entries: list[CaseEntry] = []
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_path = text_index.get(path_stem_from_row(row))
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        opinion_date = row.get("file_date", "").strip()
        year = montana_text_year(text_path)
        if not year:
            year = year_from_value(opinion_date, ["%Y-%m-%d %H:%M:%S.%f"])
        case_id = row.get("case_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = output_root / court_folder / year / case_folder
        dest_case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest_case_dir / "opinion.txt")

        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Montana Supreme Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("title", "").strip(),
                opinion_date=opinion_date,
                source_text_path=relative_str(text_path, state_root),
                output_case_path=relative_str(dest_case_dir, state_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


REORGANIZERS = {
    "florida": reorganize_florida,
    "georgia": reorganize_georgia,
    "iowa": reorganize_iowa,
    "colorado": reorganize_colorado,
    "louisiana": reorganize_louisiana,
    "maine": reorganize_maine,
    "maryland": reorganize_maryland,
    "massachusetts": reorganize_massachusetts,
    "montana": reorganize_montana,
}


STATE_ROOTS = {
    "florida": ROOT / "florida",
    "georgia": ROOT / "georgia",
    "iowa": ROOT / "iowa",
    "colorado": ROOT / "colorado",
    "louisiana": ROOT / "louisiana",
    "maine": ROOT / "maine",
    "maryland": ROOT / "maryland",
    "massachusetts": ROOT / "massachusetts",
    "montana": ROOT / "montana",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize state court opinion datasets.")
    parser.add_argument("states", nargs="*", choices=sorted(REORGANIZERS), help="State folders to reorganize")
    args = parser.parse_args()

    states = args.states or sorted(REORGANIZERS)
    for state in states:
        counts = REORGANIZERS[state](STATE_ROOTS[state])
        summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        print(f"{state}: {summary}")


if __name__ == "__main__":
    main()
