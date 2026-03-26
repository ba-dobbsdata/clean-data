"""Organiser functions for the 9 existing states.

Each function receives a ``StateConfig`` and returns a dict of counts.
All helpers and types are imported from ``reorganize_states``.

Path convention:
  cfg.raw_root  = LegalAI-Scraper/<state>/            (CSVs + raw PDFs)
  cfg.txt_root  = LegalAI-Scraper/txt_output/<state>/ (converted .txt)
  cfg.output_root = clean-data/<state>/                (organised output)
"""
from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path

from reorganize_states import (
    CaseEntry,
    StateConfig,
    build_colorado_index,
    build_text_index_by_basename,
    colorado_translation_id,
    ensure_clean_dir,
    first_regex_match,
    make_unique_case_folder,
    montana_text_year,
    parse_date,
    path_stem_from_row,
    relative_str,
    sanitize_case_component,
    slugify,
    text_path_from_flat_index,
    write_metadata,
    year_from_value,
)


# ======================================================================
# Colorado
# ======================================================================

def reorganize_colorado(cfg: StateConfig) -> dict[str, int]:
    state_name = "Colorado"
    ensure_clean_dir(cfg.output_root)

    configs = [
        {
            "csv": next((cfg.raw_root / "downloads" / "colorado_supreme_court" / "CSV").glob("*.csv")),
            "text_dir": cfg.txt_root / "download" / "colorado_supreme_court" / "pdf",
            "court_name": "Colorado Supreme Court",
            "court_folder": "supreme_court",
        },
        {
            "csv": next((cfg.raw_root / "downloads" / "colorado_court_of_appeals" / "CSV").glob("*.csv")),
            "text_dir": cfg.txt_root / "download" / "colorado_court_of_appeals" / "pdf",
            "court_name": "Colorado Court of Appeals",
            "court_folder": "court_of_appeals",
        },
    ]

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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

            dest_case_dir = cfg.output_root / config["court_folder"] / year / case_folder
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
                    source_text_path=relative_str(text_path, cfg.txt_root),
                    output_case_path=relative_str(dest_case_dir, cfg.output_root),
                    raw=raw,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Florida
# ======================================================================

def reorganize_florida(cfg: StateConfig) -> dict[str, int]:
    state_name = "Florida"
    ensure_clean_dir(cfg.output_root)

    csv_root = cfg.raw_root / "downloads"
    text_dir = cfg.txt_root / "download" / "pdf"
    text_index = {p.stem.lower(): p for p in text_dir.glob("*.txt")} if text_dir.exists() else {}

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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
            text_key = Path(row.get("pdf_file", "")).stem.lower()
            text_path = text_index.get(text_key)
            if not text_path or not text_path.exists():
                counts["rows_skipped_missing_text"] += 1
                continue

            court_code = (row.get("court") or court_dir.name).strip() or "unknown_court"
            court_folder = slugify(court_code)
            court_name = court_code
            opinion_dt = parse_date(row.get("release_date", ""), ["%m/%d/%y"])
            year = opinion_dt.strftime("%Y") if opinion_dt else ""
            if not year:
                year = year_from_value(row.get("release_date", ""), ["%m/%d/%y"])
            case_id = row.get("case_no", "").strip() or Path(row.get("pdf_file", "")).stem
            base_folder = sanitize_case_component(case_id)
            case_folder = make_unique_case_folder(
                base_folder,
                row.get("release_date", ""),
                used_folders[(court_folder, year)],
            )

            dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                    source_text_path=relative_str(text_path, cfg.txt_root),
                    output_case_path=relative_str(dest_case_dir, cfg.output_root),
                    raw=row,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Georgia
# ======================================================================

def reorganize_georgia(cfg: StateConfig) -> dict[str, int]:
    state_name = "Georgia"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "ga_supreme" / "CSV" / "ga_supreme_all_years.csv"
    # Georgia txt files are in download/ (singular), not downloads/
    text_index = build_text_index_by_basename(cfg.txt_root / "download")
    court_folder = "supreme_court"
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    entries: list[CaseEntry] = []
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        text_key = Path(row.get("pdf_file", "")).stem.lower()
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

        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# Iowa
# ======================================================================

def reorganize_iowa(cfg: StateConfig) -> dict[str, int]:
    state_name = "Iowa"
    ensure_clean_dir(cfg.output_root)

    configs = [
        {
            "csv": cfg.raw_root / "downloads" / "supreme-court" / "CSV" / "iowa_supreme_court_opinions.csv",
            "court_name": "Iowa Supreme Court",
            "court_folder": "supreme_court",
        },
        {
            "csv": cfg.raw_root / "downloads" / "court-of-appeals" / "CSV" / "iowa_court_of_appeals_opinions.csv",
            "court_name": "Iowa Court of Appeals",
            "court_folder": "court_of_appeals",
        },
    ]

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    for config in configs:
        with config["csv"].open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            counts["rows_total"] += 1
            # Iowa txt mirrors the pdf_local_path structure under txt_root/downloads/
            pdf_local = row.get("pdf_local_path", "").replace("/", "\\")
            # pdf_local_path is like: downloads/supreme-court/2023/case/file.pdf
            # txt equivalent: txt_root/downloads/supreme-court/2023/case/file.txt
            text_path = (cfg.txt_root / Path(pdf_local)).with_suffix(".txt")
            if not text_path.exists():
                counts["rows_skipped_missing_text"] += 1
                continue

            opinion_date = row.get("filed_date", "").strip()
            parsed_opinion_date = parse_date(opinion_date, ["%b %d, %Y"])
            year = parsed_opinion_date.strftime("%Y") if parsed_opinion_date else ""
            if not year:
                # Fallback: extract year from path
                parts = Path(pdf_local).parts
                for part in parts:
                    if len(part) == 4 and part.isdigit():
                        year = part
                        break
            case_id = row.get("case_no", "").strip()
            case_folder = make_unique_case_folder(
                sanitize_case_component(case_id),
                opinion_date,
                used_folders[(config["court_folder"], year)],
            )

            dest_case_dir = cfg.output_root / config["court_folder"] / year / case_folder
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
                    source_text_path=relative_str(text_path, cfg.txt_root),
                    output_case_path=relative_str(dest_case_dir, cfg.output_root),
                    raw=row,
                )
            )
            counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Louisiana
# ======================================================================

def reorganize_louisiana(cfg: StateConfig) -> dict[str, int]:
    state_name = "Louisiana"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "Louisiana_Supreme_Court" / "CSV" / "lasc_cases.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads" / "PDF")
    court_folder = "supreme_court"
    counts: dict[str, int] = {
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
        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=raw,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# Maine
# ======================================================================

def reorganize_maine(cfg: StateConfig) -> dict[str, int]:
    state_name = "Maine"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "supreme_court" / "CSV" / "supreme_court.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads" / "PDF")
    court_folder = "supreme_court"
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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

        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# Maryland
# ======================================================================

def _maryland_court_config(case_pdf_url: str) -> tuple[str, str]:
    if "/coa/" in (case_pdf_url or ""):
        return ("supreme_court", "Maryland Supreme Court")
    return ("appellate_court", "Maryland Appellate Court")


def reorganize_maryland(cfg: StateConfig) -> dict[str, int]:
    state_name = "Maryland"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "appellate_court_opinions" / "CSV" / "cases.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads" / "PDF")
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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

        court_folder, court_name = _maryland_court_config(row.get("case_pdf_url", ""))
        # filed_date may contain annotations like "corrected 2026-03-06" -- extract date
        opinion_date = first_regex_match(row.get("filed_date", ""), r"((?:19|20)\d{2}-\d{2}-\d{2})")
        year = year_from_value(opinion_date, ["%Y-%m-%d"])
        case_id = (row.get("docket_term", "").strip() or text_path.stem).replace("/", "-")
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            opinion_date,
            used_folders[(court_folder, year)],
        )

        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=raw,
            )
        )
        counts["cases_retained"] += 1

    for court_folder, entries in court_entries.items():
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Massachusetts
# ======================================================================

def reorganize_massachusetts(cfg: StateConfig) -> dict[str, int]:
    state_name = "Massachusetts"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "appeals_court" / "CSV" / "appeals_court_cases.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads" / "PDF")
    court_folder = "appeals_court"
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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

        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# Montana
# ======================================================================

def reorganize_montana(cfg: StateConfig) -> dict[str, int]:
    state_name = "Montana"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "supreme_court" / "CSV" / "supreme_court_daily_orders.csv"
    # Montana may have 0 txt files -- index whatever exists
    txt_pdf_dir = cfg.txt_root / "downloads" / "PDF"
    text_index = build_text_index_by_basename(txt_pdf_dir) if txt_pdf_dir.exists() else {}
    court_folder = "supreme_court"
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
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

        dest_case_dir = cfg.output_root / court_folder / year / case_folder
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
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest_case_dir, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# Registry
# ======================================================================

REORGANIZERS = {
    "colorado": reorganize_colorado,
    "florida": reorganize_florida,
    "georgia": reorganize_georgia,
    "iowa": reorganize_iowa,
    "louisiana": reorganize_louisiana,
    "maine": reorganize_maine,
    "maryland": reorganize_maryland,
    "massachusetts": reorganize_massachusetts,
    "montana": reorganize_montana,
}
