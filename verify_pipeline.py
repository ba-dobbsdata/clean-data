"""3-Level verification pipeline for state court opinion organisation.

Levels:
  Level 1  Raw PDFs       LegalAI-Scraper/<state>/downloads/  (or download/)
  Level 2  Converted txt  LegalAI-Scraper/txt_output/<state>/
  Level 3  Organised      clean-data/<state>/

Diffs:
  Diff 1  Level 1 vs Level 2  →  PDFs that failed txt conversion
  Diff 2  Level 2 vs Level 3  →  txt files not organised
  Diff 3  Level 3 internal    →  metadata rows vs folders vs opinion.txt

Output:
  <state>_verification.csv  per-state detail report
  Summary printed to stdout
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent           # LegalAI-Scraper/
RAW_ROOT = PROJECT_ROOT                            # CSVs + PDFs
TXT_ROOT = PROJECT_ROOT / "txt_output"             # converted .txt
OUTPUT_ROOT = SCRIPT_DIR                           # clean-data/ (organised)

REPORT_DIR = SCRIPT_DIR / "verification_reports"

ALL_STATES = [
    "colorado",
    "florida",
    "georgia",
    "iowa",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "montana",
    "nevada",
    "new_hampshire",
    "new_jersey",
    "new_mexico",
    "north_carolina",
    "pennsylvania",
    "rhode_island",
    "south_carolina",
    "vermont",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_files(root: Path, suffix: str) -> set[str]:
    """Return lowercased stems of all files with *suffix* under *root*."""
    if not root.exists():
        return set()
    return {p.stem.lower() for p in root.rglob(f"*{suffix}")}


def _collect_files_full(root: Path, suffix: str) -> dict[str, Path]:
    """Return mapping of lowercased stem → Path for files with *suffix*."""
    if not root.exists():
        return {}
    return {p.stem.lower(): p for p in root.rglob(f"*{suffix}")}


def _count_files(root: Path, suffix: str) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob(f"*{suffix}"))


# ---------------------------------------------------------------------------
# Level 1: Count raw PDFs
# ---------------------------------------------------------------------------

def level1_pdfs(state: str) -> dict[str, int]:
    """Count PDF files under RAW_ROOT/<state>/downloads/ (or download/)."""
    raw = RAW_ROOT / state
    counts: dict[str, int] = {}

    for subdir_name in ("downloads", "download"):
        subdir = raw / subdir_name
        if subdir.exists():
            n = _count_files(subdir, ".pdf")
            if n > 0:
                counts[subdir_name] = n

    total = sum(counts.values())
    counts["total_pdfs"] = total
    return counts


def level1_pdf_stems(state: str) -> set[str]:
    """Collect lowercased stems of all PDFs for a state."""
    raw = RAW_ROOT / state
    stems: set[str] = set()
    for subdir_name in ("downloads", "download"):
        subdir = raw / subdir_name
        stems |= _collect_files(subdir, ".pdf")
    return stems


# ---------------------------------------------------------------------------
# Level 2: Count txt files
# ---------------------------------------------------------------------------

def level2_txts(state: str) -> dict[str, int]:
    """Count txt files under TXT_ROOT/<state>/."""
    txt = TXT_ROOT / state
    total = _count_files(txt, ".txt")
    return {"total_txts": total}


def level2_txt_stems(state: str) -> set[str]:
    """Collect lowercased stems of all txt files for a state."""
    txt = TXT_ROOT / state
    return _collect_files(txt, ".txt")


# ---------------------------------------------------------------------------
# Level 3: Count organised output
# ---------------------------------------------------------------------------

def level3_organised(state: str) -> dict[str, object]:
    """Analyse the organised output for a state.

    Returns:
      courts: list of court folder names
      opinion_txts: total opinion.txt files
      metadata_rows: total rows across all metadata CSVs
      folders_with_opinion: count of case folders containing opinion.txt
      folders_without_opinion: count of case folders missing opinion.txt
    """
    out = OUTPUT_ROOT / state
    if not out.exists():
        return {
            "courts": [],
            "opinion_txts": 0,
            "metadata_rows": 0,
            "folders_with_opinion": 0,
            "folders_without_opinion": 0,
        }

    courts: list[str] = []
    opinion_count = 0
    metadata_rows = 0
    folders_with = 0
    folders_without = 0

    for court_dir in sorted(out.iterdir()):
        if not court_dir.is_dir():
            continue
        courts.append(court_dir.name)

        # Count metadata rows
        meta_csv = court_dir / f"{court_dir.name}_metadata.csv"
        if meta_csv.exists():
            with meta_csv.open(newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                metadata_rows += sum(1 for _ in reader)

        # Walk year/case folders
        for year_dir in sorted(court_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for case_dir in sorted(year_dir.iterdir()):
                if not case_dir.is_dir():
                    continue
                opinion = case_dir / "opinion.txt"
                if opinion.exists():
                    opinion_count += 1
                    folders_with += 1
                else:
                    folders_without += 1

    return {
        "courts": courts,
        "opinion_txts": opinion_count,
        "metadata_rows": metadata_rows,
        "folders_with_opinion": folders_with,
        "folders_without_opinion": folders_without,
    }


def level3_opinion_stems(state: str) -> set[str]:
    """Collect lowercased stems of source_text_path from metadata CSVs.

    This tells us which txt stems were actually organised.
    """
    out = OUTPUT_ROOT / state
    stems: set[str] = set()
    if not out.exists():
        return stems

    for meta_csv in out.rglob("*_metadata.csv"):
        with meta_csv.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                src = row.get("source_text_path", "")
                if src:
                    stems.add(Path(src).stem.lower())
    return stems


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diffs(state: str) -> dict[str, object]:
    """Compute all three diffs for a state."""
    pdf_stems = level1_pdf_stems(state)
    txt_stems = level2_txt_stems(state)
    organised_stems = level3_opinion_stems(state)

    # Diff 1: PDFs without corresponding txt
    diff1 = pdf_stems - txt_stems

    # Diff 2: txt files not organised
    diff2 = txt_stems - organised_stems

    # Diff 3: internal consistency
    l3 = level3_organised(state)
    meta_rows = l3["metadata_rows"]
    opinion_txts = l3["opinion_txts"]
    diff3_meta_vs_files = meta_rows - opinion_txts  # positive = metadata rows with no opinion.txt

    return {
        "diff1_pdf_no_txt": sorted(diff1),
        "diff1_count": len(diff1),
        "diff2_txt_not_organised": sorted(diff2),
        "diff2_count": len(diff2),
        "diff3_metadata_minus_opinions": diff3_meta_vs_files,
        "folders_without_opinion": l3["folders_without_opinion"],
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(state: str) -> dict[str, object]:
    """Generate a full verification report for a state."""
    l1 = level1_pdfs(state)
    l2 = level2_txts(state)
    l3 = level3_organised(state)
    diffs = compute_diffs(state)

    report = {
        "state": state,
        "level1_total_pdfs": l1.get("total_pdfs", 0),
        "level2_total_txts": l2.get("total_txts", 0),
        "level3_courts": l3["courts"],
        "level3_opinion_txts": l3["opinion_txts"],
        "level3_metadata_rows": l3["metadata_rows"],
        "level3_folders_with_opinion": l3["folders_with_opinion"],
        "level3_folders_without_opinion": l3["folders_without_opinion"],
        "diff1_pdf_no_txt_count": diffs["diff1_count"],
        "diff2_txt_not_organised_count": diffs["diff2_count"],
        "diff3_metadata_minus_opinions": diffs["diff3_metadata_minus_opinions"],
    }
    return report


def write_detail_csv(state: str, diffs: dict[str, object]) -> Path:
    """Write a per-state detail CSV with individual missing items."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORT_DIR / f"{state}_verification.csv"

    rows: list[dict[str, str]] = []

    for stem in diffs["diff1_pdf_no_txt"]:
        rows.append({
            "state": state,
            "issue_type": "pdf_no_txt",
            "item": stem,
            "detail": "PDF exists but no txt conversion found",
        })

    for stem in diffs["diff2_txt_not_organised"]:
        rows.append({
            "state": state,
            "issue_type": "txt_not_organised",
            "item": stem,
            "detail": "txt exists but was not included in organised output",
        })

    if diffs["diff3_metadata_minus_opinions"] != 0:
        rows.append({
            "state": state,
            "issue_type": "metadata_opinion_mismatch",
            "item": "",
            "detail": f"metadata_rows - opinion.txt = {diffs['diff3_metadata_minus_opinions']}",
        })

    if diffs["folders_without_opinion"] > 0:
        rows.append({
            "state": state,
            "issue_type": "folder_missing_opinion",
            "item": "",
            "detail": f"{diffs['folders_without_opinion']} case folder(s) without opinion.txt",
        })

    fieldnames = ["state", "issue_type", "item", "detail"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return csv_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="3-level verification of state court opinion pipeline.",
    )
    parser.add_argument(
        "states", nargs="*",
        help=f"States to verify (default: all). Choices: {', '.join(ALL_STATES)}",
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="Write per-state detail CSVs listing every missing item",
    )
    args = parser.parse_args()

    states = args.states or ALL_STATES
    # Validate
    for s in states:
        if s not in ALL_STATES:
            parser.error(f"Unknown state: {s}")

    summary_rows: list[dict[str, object]] = []

    for state in states:
        report = generate_report(state)
        summary_rows.append(report)

        courts_str = ", ".join(report["level3_courts"]) if report["level3_courts"] else "(none)"
        print(f"\n{'='*60}")
        print(f"  {state.upper()}")
        print(f"{'='*60}")
        print(f"  Level 1 – Raw PDFs:          {report['level1_total_pdfs']:>8,}")
        print(f"  Level 2 – Converted txt:     {report['level2_total_txts']:>8,}")
        print(f"  Level 3 – Organised opinions:{report['level3_opinion_txts']:>8,}")
        print(f"            Metadata rows:     {report['level3_metadata_rows']:>8,}")
        print(f"            Courts: {courts_str}")
        print(f"  Diff 1 (PDF→txt missing):    {report['diff1_pdf_no_txt_count']:>8,}")
        print(f"  Diff 2 (txt not organised):  {report['diff2_txt_not_organised_count']:>8,}")
        print(f"  Diff 3 (meta-opinion delta): {report['diff3_metadata_minus_opinions']:>8,}")
        print(f"          Folders w/o opinion:  {report['level3_folders_without_opinion']:>8,}")

        if args.detail:
            diffs = compute_diffs(state)
            csv_path = write_detail_csv(state, diffs)
            total_issues = (
                diffs["diff1_count"]
                + diffs["diff2_count"]
                + (1 if diffs["diff3_metadata_minus_opinions"] != 0 else 0)
                + (1 if diffs["folders_without_opinion"] > 0 else 0)
            )
            print(f"  Detail CSV: {csv_path}  ({total_issues} issue rows)")

    # Summary table
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"{'State':<20} {'PDFs':>8} {'Txts':>8} {'Organised':>10} {'D1':>6} {'D2':>6} {'D3':>6}")
    print(f"{'-'*20} {'-'*8} {'-'*8} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")
    for r in summary_rows:
        print(
            f"{r['state']:<20} "
            f"{r['level1_total_pdfs']:>8,} "
            f"{r['level2_total_txts']:>8,} "
            f"{r['level3_opinion_txts']:>10,} "
            f"{r['diff1_pdf_no_txt_count']:>6,} "
            f"{r['diff2_txt_not_organised_count']:>6,} "
            f"{r['diff3_metadata_minus_opinions']:>6}"
        )

    total_pdfs = sum(r["level1_total_pdfs"] for r in summary_rows)
    total_txts = sum(r["level2_total_txts"] for r in summary_rows)
    total_org = sum(r["level3_opinion_txts"] for r in summary_rows)
    total_d1 = sum(r["diff1_pdf_no_txt_count"] for r in summary_rows)
    total_d2 = sum(r["diff2_txt_not_organised_count"] for r in summary_rows)
    print(f"{'-'*20} {'-'*8} {'-'*8} {'-'*10} {'-'*6} {'-'*6} {'-'*6}")
    print(
        f"{'TOTAL':<20} "
        f"{total_pdfs:>8,} "
        f"{total_txts:>8,} "
        f"{total_org:>10,} "
        f"{total_d1:>6,} "
        f"{total_d2:>6,} "
        f"{'':>6}"
    )


if __name__ == "__main__":
    main()
