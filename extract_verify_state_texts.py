from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parent


STATE_CONFIGS = {
    "maryland": {
        "verify_csv": ROOT / "verify-data" / "maryland" / "downloads" / "appellate_court_opinions" / "CSV" / "cases.csv",
        "verify_root": ROOT / "verify-data" / "maryland" / "downloads",
        "output_dir": ROOT / "maryland" / "downloads" / "PDF",
    },
    "montana": {
        "verify_csv": ROOT / "verify-data" / "montana" / "downloads" / "supreme_court" / "CSV" / "supreme_court_daily_orders.csv",
        "verify_root": ROOT / "verify-data" / "montana" / "downloads",
        "output_dir": ROOT / "montana" / "downloads" / "PDF",
    },
}


def extract_pdf(pdf_path: Path, output_path: Path) -> tuple[bool, str]:
    try:
        reader = PdfReader(str(pdf_path))
        text_parts: list[str] = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if not text:
            return (False, "empty_text")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        return (True, "extracted")
    except Exception as exc:  # pragma: no cover - batch robustness
        return (False, f"error:{type(exc).__name__}:{exc}")


def build_jobs(state: str) -> list[tuple[Path, Path]]:
    config = STATE_CONFIGS[state]
    jobs: list[tuple[Path, Path]] = []
    seen_outputs: set[Path] = set()
    pdf_index = {path.name: path for path in config["verify_root"].rglob("*.pdf")}

    with config["verify_csv"].open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            pdf_local_path = Path(row["pdf_local_path"].replace("\\", "/"))
            pdf_name = pdf_local_path.name
            pdf_path = pdf_index.get(pdf_name)
            if not pdf_path:
                continue

            output_path = config["output_dir"] / f"{pdf_path.stem}.txt"
            if output_path in seen_outputs:
                continue
            seen_outputs.add(output_path)
            jobs.append((pdf_path, output_path))
    return jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract authoritative PDFs to local flat text corpora.")
    parser.add_argument("states", nargs="+", choices=sorted(STATE_CONFIGS))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    for state in args.states:
        jobs = build_jobs(state)
        extracted = 0
        skipped_existing = 0
        empty_text = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            for pdf_path, output_path in jobs:
                if output_path.exists() and output_path.stat().st_size > 0:
                    skipped_existing += 1
                    continue
                futures[executor.submit(extract_pdf, pdf_path, output_path)] = output_path

            for future in as_completed(futures):
                ok, status = future.result()
                if status == "extracted":
                    extracted += 1
                elif status == "empty_text":
                    empty_text += 1
                else:
                    errors += 1

        print(
            f"{state}: jobs_total={len(jobs)}, extracted={extracted}, "
            f"skipped_existing={skipped_existing}, empty_text={empty_text}, errors={errors}"
        )


if __name__ == "__main__":
    main()
