"""Organiser functions for the 9 new states.

Each function receives a ``StateConfig`` and returns a dict of counts.
All helpers and types are imported from ``reorganize_states``.

Path convention:
  cfg.raw_root  = LegalAI-Scraper/<state>/            (CSVs + raw PDFs)
  cfg.txt_root  = LegalAI-Scraper/txt_output/<state>/ (converted .txt)
  cfg.output_root = clean-data/<state>/                (organised output)
"""
from __future__ import annotations

import csv
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from reorganize_states import (
    CaseEntry,
    StateConfig,
    build_text_index_by_basename,
    ensure_clean_dir,
    make_unique_case_folder,
    normalize_nj_date,
    parse_date,
    relative_str,
    sanitize_case_component,
    slugify,
    write_metadata,
    year_from_value,
)


# ======================================================================
# Nevada
# ======================================================================

def reorganize_nevada(cfg: StateConfig) -> dict[str, int]:
    """Nevada: 2 court types determined by ``source_type``.

    - advance_opinions  → opinion_date
    - unpublished_orders → order_date

    txt mirrors pdf_local_path under txt_root with .pdf→.txt.
    """
    state_name = "Nevada"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "case.csv"
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
        pdf_local = row.get("pdf_local_path", "").strip()
        if not pdf_local:
            counts["rows_skipped_missing_text"] += 1
            continue

        text_path = (cfg.txt_root / Path(pdf_local)).with_suffix(".txt")
        if not text_path.exists():
            counts["rows_skipped_missing_text"] += 1
            continue

        source_type = row.get("source_type", "").strip().lower()
        if "advance" in source_type:
            court_folder = "advance_opinions"
            court_name = "Nevada Supreme Court – Advance Opinions"
            date_raw = row.get("opinion_date", "").strip()
        else:
            court_folder = "unpublished_orders"
            court_name = "Nevada Supreme Court – Unpublished Orders"
            date_raw = row.get("order_date", "").strip()

        year = year_from_value(date_raw, ["%b %d, %Y", "%B %d, %Y"])
        case_id = row.get("case_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_title", row.get("title", "")).strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# New Hampshire
# ======================================================================

def reorganize_new_hampshire(cfg: StateConfig) -> dict[str, int]:
    """New Hampshire: 4 court categories from ``court`` column.

    txt mirrors pdf_local_path under txt_root with .pdf→.txt.
    3jx_final_orders has empty case_date — derive year from path.
    """
    state_name = "New Hampshire"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "supreme_court" / "CSV" / "case.csv"
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "opinions": ("opinions", "NH Supreme Court – Opinions"),
        "case-orders": ("case_orders", "NH Supreme Court – Case Orders"),
        "3jx-final-orders": ("3jx_final_orders", "NH Supreme Court – 3JX Final Orders"),
        "supervisory-orders": ("supervisory_orders", "NH Supreme Court – Supervisory Orders"),
    }

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        pdf_local = row.get("pdf_local_path", "").strip()
        if not pdf_local:
            counts["rows_skipped_missing_text"] += 1
            continue

        # Handle absolute Windows paths: extract relative path from 'downloads/' onwards
        pdf_local_normalized = pdf_local.replace("\\", "/")
        if "downloads/" in pdf_local_normalized:
            pdf_local_rel = "downloads/" + pdf_local_normalized.split("downloads/", 1)[1]
        else:
            pdf_local_rel = pdf_local_normalized
        text_path = (cfg.txt_root / Path(pdf_local_rel)).with_suffix(".txt")
        if not text_path.exists():
            counts["rows_skipped_missing_text"] += 1
            continue

        court_key = row.get("court", "").strip().lower()
        court_folder, court_name = COURT_MAP.get(court_key, (slugify(court_key), court_key))

        date_raw = row.get("case_date", "").strip()
        year = year_from_value(date_raw, ["%Y-%m-%d", "%d/%m/%y", "%m/%d/%y"])
        if year == "unknown_year":
            # Fallback: extract year from pdf_local_path (use normalized path)
            match = re.search(r"/(?:19|20)\d{2}/", pdf_local_normalized)
            if match:
                year = match.group(0).strip("/")
            else:
                # Try 4-digit component from path parts
                for part in Path(pdf_local).parts:
                    if len(part) == 4 and part.isdigit():
                        year = part
                        break

        case_id = row.get("case_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_title", row.get("title", "")).strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# New Jersey
# ======================================================================

def reorganize_new_jersey(cfg: StateConfig) -> dict[str, int]:
    """New Jersey: 3 court types from ``source_court``.

    txt files live in txt_output/new_jersey/download/<court>/file/*.txt.
    Matching: build basename index from all txt under txt_root/download/.
    """
    state_name = "New Jersey"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "case.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "download")
    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "supreme": ("supreme", "New Jersey Supreme Court"),
        "appellate": ("published_appellate", "NJ Appellate Division – Published"),
        "appellate_unpublished": ("unpublished_appellate", "NJ Appellate Division – Unpublished"),
    }

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1

        # NJ txt files are named {case_no}_{pdf_stem}.txt
        # pdf_full_path is like: downloads\Supreme\2026\A-36-24\a_36_37_38_39_24.pdf
        case_no = row.get("no", "").strip()
        pdf_full = row.get("pdf_full_path", "").strip()
        text_path = None
        if case_no and pdf_full:
            pdf_stem = Path(pdf_full.replace("\\", "/")).stem
            # Construct the expected txt stem: case_no_pdf_stem
            expected_stem = f"{case_no}_{pdf_stem}".lower()
            text_path = text_index.get(expected_stem)
        
        # Fallback: try just the pdf stem
        if not text_path and pdf_full:
            stem = Path(pdf_full.replace("\\", "/")).stem.lower()
            text_path = text_index.get(stem)

        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        source_court = row.get("source_court", "").strip().lower()
        court_folder, court_name = COURT_MAP.get(
            source_court,
            (slugify(source_court) or "unknown_court", source_court),
        )

        date_raw = row.get("date", "").strip()
        normalized_date = normalize_nj_date(date_raw)
        year = year_from_value(normalized_date, ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"])
        case_id = case_no or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("title", "").strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# New Mexico
# ======================================================================

def reorganize_new_mexico(cfg: StateConfig) -> dict[str, int]:
    """New Mexico: 2 courts from ``court`` column.

    txt in txt_output/new_mexico/downloads/<court>/PDF/*.txt.
    Match by item_id extracted from txt filename via regex.
    """
    state_name = "New Mexico"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "case.csv"

    # Build index: item_id → txt Path
    # NM txt filenames are like: 01-01-1852_369690_Bray v. United States.txt
    # Extract item_id (the numeric part between underscores)
    text_index_sc: dict[str, Path] = {}
    text_index_ca: dict[str, Path] = {}

    sc_dir = cfg.txt_root / "downloads" / "supreme_court" / "PDF"
    ca_dir = cfg.txt_root / "downloads" / "court_of_appeals" / "PDF"

    for txt_dir, idx in [(sc_dir, text_index_sc), (ca_dir, text_index_ca)]:
        if not txt_dir.exists():
            continue
        for p in txt_dir.glob("*.txt"):
            # Extract item_id from filename: date_itemid_title.txt
            parts = p.stem.split("_")
            if len(parts) >= 2:
                # item_id is typically the second part (numeric)
                item_id_candidate = parts[1]
                if item_id_candidate.isdigit():
                    idx[item_id_candidate] = p
            # Also index by full stem as fallback
            idx[p.stem.lower()] = p

    # Also build a combined basename index for fallback
    all_txt_index = build_text_index_by_basename(cfg.txt_root / "downloads")

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "supreme_court_of_new_mexico": ("supreme_court", "New Mexico Supreme Court"),
        "supreme_court": ("supreme_court", "New Mexico Supreme Court"),
        "court_of_appeals_of_new_mexico": ("court_of_appeals", "New Mexico Court of Appeals"),
        "court_of_appeals": ("court_of_appeals", "New Mexico Court of Appeals"),
    }

    # Track which court_raw values map to which index
    SC_COURTS = {"supreme_court_of_new_mexico", "supreme_court"}

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        item_id = row.get("item_id", "").strip()
        court_raw = row.get("court", "").strip().lower().replace(" ", "_")
        court_folder, court_name = COURT_MAP.get(
            court_raw,
            (slugify(court_raw) or "unknown_court", court_raw),
        )

        # Try to find txt via item_id first (txt files indexed by item_id)
        text_path = None
        if item_id:
            if court_raw in SC_COURTS:
                text_path = text_index_sc.get(item_id)
            else:
                text_path = text_index_ca.get(item_id)
        
        # Fallback: try pdf_local_path stem (which is also item_id)
        if not text_path:
            pdf_local = row.get("pdf_local_path", "").strip()
            if pdf_local:
                stem = Path(pdf_local.replace("\\", "/")).stem.lower()
                if court_raw in SC_COURTS:
                    text_path = text_index_sc.get(stem)
                else:
                    text_path = text_index_ca.get(stem)
                if not text_path:
                    text_path = all_txt_index.get(stem)

        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        date_raw = row.get("publication_date", "").strip()
        year = year_from_value(date_raw, ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"])
        case_id = item_id or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("title", "").strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# North Carolina
# ======================================================================

def _nc_pdf_id_from_url(pdf_url: str) -> str:
    """Extract a unique identifier from a North Carolina pdf_url.

    The URL typically looks like:
      https://appellate.nccourts.org/opinions/?c=2&pdf=45475
    We extract the 'pdf' query parameter as the key.
    """
    if not pdf_url:
        return ""
    parsed = urlparse(pdf_url)
    qs = parse_qs(parsed.query)
    
    # Try 'pdf' parameter first (most common)
    pdf_id = qs.get("pdf", [""])[0]
    if pdf_id:
        return pdf_id.lower()
    
    # Fallback: try filename stem + VersionId
    stem = Path(parsed.path).stem
    version = qs.get("VersionId", [""])[0]
    if version:
        return f"{stem}_{version}".lower()
    return stem.lower()


def reorganize_north_carolina(cfg: StateConfig) -> dict[str, int]:
    """North Carolina: 3 courts from ``court`` column.

    txt all in one dir: txt_output/north_carolina/download/appellate_court_opinions/file/*.txt
    Supreme + Court of Appeals share that directory; Business Court may be separate.
    Match by pdf_url filename stem.
    """
    state_name = "North Carolina"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "north_carolina_opinions_merged.csv"

    # Build text index by numeric pdf_id suffix from filenames like "Title_12345.txt"
    # The pdf_id corresponds to the 'pdf' query param in the CSV's pdf_url
    txt_dir = cfg.txt_root / "download" / "appellate_court_opinions" / "file"
    text_index: dict[str, Path] = {}
    if txt_dir.exists():
        for p in txt_dir.glob("*.txt"):
            # Extract numeric suffix: "Title Name_12345.txt" -> "12345"
            parts = p.stem.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                text_index[parts[1]] = p
            # Also index by full stem for fallback
            text_index[p.stem.lower()] = p

    # Also check for business court txt in a separate location
    biz_txt_dir = cfg.txt_root / "download" / "business_court_opinions" / "file"
    if biz_txt_dir.exists():
        for p in biz_txt_dir.glob("*.txt"):
            parts = p.stem.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                text_index.setdefault(parts[1], p)
            text_index.setdefault(p.stem.lower(), p)

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "supreme_court": ("supreme_court", "North Carolina Supreme Court"),
        "court_of_appeals": ("court_of_appeals", "North Carolina Court of Appeals"),
        "business_court": ("business_court", "North Carolina Business Court"),
    }

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1

        pdf_url = row.get("pdf_url", "").strip()
        zip_url = row.get("zip_url", "").strip()

        # Try to match txt file by pdf_id from 'pdf' query param
        text_path = None
        if pdf_url:
            parsed = urlparse(pdf_url)
            qs = parse_qs(parsed.query)
            pdf_id = qs.get("pdf", [""])[0]
            if pdf_id:
                text_path = text_index.get(pdf_id)
            if not text_path:
                # Fallback: try URL path stem
                stem = Path(parsed.path).stem.lower()
                text_path = text_index.get(stem)

        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        court_raw = row.get("court", "").strip().lower().replace(" ", "_")
        court_folder, court_name = COURT_MAP.get(
            court_raw,
            (slugify(court_raw) or "unknown_court", court_raw),
        )

        date_raw = row.get("date", "").strip()
        year = year_from_value(date_raw, ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"])
        # Use pdf_url-based ID since docket column is useless
        case_id = _nc_pdf_id_from_url(pdf_url) or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("title", "").strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Pennsylvania
# ======================================================================

def reorganize_pennsylvania(cfg: StateConfig) -> dict[str, int]:
    """Pennsylvania: 5 court sources from ``source`` column.

    txt in flat dir: txt_output/pennsylvania/downloads/*.txt
    pdf_file column contains filename; extract case key from portion after ``__``.
    aopc_web_public may contain non-opinion admin docs — include but separate.
    """
    state_name = "Pennsylvania"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "all_courts.csv"
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads")

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "opinions-supreme": ("opinions_supreme", "PA Supreme Court"),
        "opinions-superior": ("opinions_superior", "PA Superior Court"),
        "opinions-commonwealth": ("opinions_commonwealth", "PA Commonwealth Court"),
        "opinions-disciplinaryboard": ("opinions_disciplinaryboard", "PA Disciplinary Board"),
        "aopc-web-public": ("aopc_web_public", "PA AOPC Web Public"),
    }

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1
        pdf_file = row.get("pdf_file", "").strip()
        if not pdf_file:
            counts["rows_skipped_missing_text"] += 1
            continue

        # Normalize backslashes for cross-platform path handling
        stem = Path(pdf_file.replace("\\", "/")).stem.lower()
        text_path = text_index.get(stem)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        source = row.get("source", "").strip().lower()
        court_folder, court_name = COURT_MAP.get(
            source,
            (slugify(source) or "unknown_court", source),
        )

        date_raw = row.get("date", "").strip()
        year = year_from_value(date_raw, ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"])

        # Extract case key from the portion after '__' in pdf_file
        pdf_stem = Path(pdf_file.replace("\\", "/")).stem
        if "__" in pdf_stem:
            case_id = pdf_stem.split("__", 1)[1]
        else:
            case_id = pdf_stem
        case_id = case_id.strip() or text_path.stem

        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("title", "").strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Rhode Island
# ======================================================================

def reorganize_rhode_island(cfg: StateConfig) -> dict[str, int]:
    """Rhode Island: 1 court (supreme_court).

    txt in hierarchical: txt_output/rhode_island/downloads/supreme_court/<year>/<case>/*.txt
    Match by pdf_local_path .pdf→.txt.
    """
    state_name = "Rhode Island"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "supreme_court" / "CSV" / "supreme_court_cases.csv"
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
        pdf_local = row.get("pdf_local_path", "").strip()
        if not pdf_local:
            counts["rows_skipped_missing_text"] += 1
            continue

        # Handle absolute Windows paths: extract relative path from 'downloads/' onwards
        pdf_local_normalized = pdf_local.replace("\\", "/")
        if "downloads/" in pdf_local_normalized:
            pdf_local_rel = "downloads/" + pdf_local_normalized.split("downloads/", 1)[1]
        else:
            pdf_local_rel = pdf_local_normalized
        text_path = (cfg.txt_root / Path(pdf_local_rel)).with_suffix(".txt")
        if not text_path.exists():
            counts["rows_skipped_missing_text"] += 1
            continue

        # case_date format: "Wednesday, January 15, 2025"
        date_raw = row.get("case_date", "").strip()
        year = year_from_value(date_raw, ["%A, %B %d, %Y", "%B %d, %Y"])
        case_id = row.get("case_number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        entries.append(
            CaseEntry(
                state=state_name,
                court_name="Rhode Island Supreme Court",
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("case_title", row.get("title", "")).strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    if entries:
        write_metadata(cfg.output_root / court_folder, court_folder, entries)
        counts["courts"] = 1
    return counts


# ======================================================================
# South Carolina
# ======================================================================

def reorganize_south_carolina(cfg: StateConfig) -> dict[str, int]:
    """South Carolina: 4 court folders from ``Court`` + ``Type``.

    CSV column names have typos: ``Donwload PDF path``, ``descpiction``.
    txt flat in txt_output/south_carolina/downloads/<court>/PDF/*.txt.
    """
    state_name = "South Carolina"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "case.csv"
    # Build index across all court PDF dirs
    text_index = build_text_index_by_basename(cfg.txt_root / "downloads")

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    def _sc_court_folder(court: str, pub_type: str) -> tuple[str, str]:
        court_lower = court.lower()
        pub_lower = pub_type.lower()
        if "supreme" in court_lower:
            if "unpub" in pub_lower:
                return ("unpublished_supreme_court", "SC Supreme Court – Unpublished")
            return ("published_supreme_court", "SC Supreme Court – Published")
        else:
            if "unpub" in pub_lower:
                return ("unpublished_court_of_appeals", "SC Court of Appeals – Unpublished")
            return ("published_court_of_appeals", "SC Court of Appeals – Published")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1

        # Handle misspelled column: "Donwload PDF path"
        pdf_path_raw = row.get("Donwload PDF path", row.get("Download PDF path", "")).strip()
        case_no = row.get("case_no", "").strip()

        # Try matching by case_no stem, then by pdf path stem
        text_path = None
        if case_no:
            text_path = text_index.get(case_no.lower())
        if not text_path and pdf_path_raw:
            stem = Path(pdf_path_raw).stem.lower()
            text_path = text_index.get(stem)

        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        court_raw = row.get("Court", "").strip()
        type_raw = row.get("Type", "").strip()
        court_folder, court_name = _sc_court_folder(court_raw, type_raw)

        # Date column is ALL CAPS month names: "JANUARY 15, 2025"
        date_raw = row.get("Date", "").strip()
        # Normalise to title case for parsing
        date_normalised = date_raw.title() if date_raw else ""
        year = year_from_value(date_normalised, ["%B %d, %Y", "%b %d, %Y"])
        case_id = case_no or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("descpiction", row.get("description", "")).strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Vermont
# ======================================================================

def reorganize_vermont(cfg: StateConfig) -> dict[str, int]:
    """Vermont: 7 court types from ``Court`` column.

    0 txt files currently — needs PDF extraction first.
    PDF filenames are irregular. Match by ``Opinion folder (PDF full path)`` stem.
    """
    state_name = "Vermont"
    ensure_clean_dir(cfg.output_root)

    csv_path = cfg.raw_root / "downloads" / "CSV" / "case.csv"
    # Build index from whatever txt files exist (may be 0)
    txt_base = cfg.txt_root / "downloads"
    text_index = build_text_index_by_basename(txt_base) if txt_base.exists() else {}

    counts: dict[str, int] = {
        "rows_total": 0,
        "cases_retained": 0,
        "rows_skipped_missing_text": 0,
        "courts": 0,
    }
    court_entries: dict[str, list[CaseEntry]] = defaultdict(list)
    used_folders: dict[tuple[str, str], set[str]] = defaultdict(set)

    COURT_MAP = {
        "supreme court": ("supreme_court", "Vermont Supreme Court"),
        "civil": ("civil", "Vermont Civil Division"),
        "criminal": ("criminal", "Vermont Criminal Division"),
        "environmental": ("environmental", "Vermont Environmental Division"),
        "family": ("family", "Vermont Family Division"),
        "probate": ("probate", "Vermont Probate Division"),
    }

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        counts["rows_total"] += 1

        pdf_full = row.get("Opinion folder (PDF full path)", "").strip()
        if not pdf_full:
            counts["rows_skipped_missing_text"] += 1
            continue

        stem = Path(pdf_full).stem.lower()
        text_path = text_index.get(stem)
        if not text_path:
            counts["rows_skipped_missing_text"] += 1
            continue

        court_raw = row.get("Court", "").strip().lower()
        court_folder, court_name = COURT_MAP.get(
            court_raw,
            (slugify(court_raw) or "unknown_court", row.get("Court", "").strip() or "Unknown Court"),
        )

        date_raw = row.get("Date", "").strip()
        year = year_from_value(date_raw, ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"])
        case_id = row.get("Case Number", "").strip() or text_path.stem
        case_folder = make_unique_case_folder(
            sanitize_case_component(case_id),
            date_raw,
            used_folders[(court_folder, year)],
        )

        dest = cfg.output_root / court_folder / year / case_folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(text_path, dest / "opinion.txt")

        court_entries[court_folder].append(
            CaseEntry(
                state=state_name,
                court_name=court_name,
                court_folder=court_folder,
                year=year,
                case_id=case_id,
                case_folder=case_folder,
                case_title=row.get("Case Name", row.get("title", "")).strip(),
                opinion_date=date_raw,
                source_text_path=relative_str(text_path, cfg.txt_root),
                output_case_path=relative_str(dest, cfg.output_root),
                raw=row,
            )
        )
        counts["cases_retained"] += 1

    for cf, entries in court_entries.items():
        write_metadata(cfg.output_root / cf, cf, entries)
    counts["courts"] = len(court_entries)
    return counts


# ======================================================================
# Registry
# ======================================================================

REORGANIZERS = {
    "nevada": reorganize_nevada,
    "new_hampshire": reorganize_new_hampshire,
    "new_jersey": reorganize_new_jersey,
    "new_mexico": reorganize_new_mexico,
    "north_carolina": reorganize_north_carolina,
    "pennsylvania": reorganize_pennsylvania,
    "rhode_island": reorganize_rhode_island,
    "south_carolina": reorganize_south_carolina,
    "vermont": reorganize_vermont,
}
