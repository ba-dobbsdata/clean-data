from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parent
VERIFY_DOWNLOADS = ROOT / "verify-data" / "florida" / "downloads"
OUTPUT_ROOT = ROOT / "florida" / "download" / "verify_text"


def extract_pdf(pdf_path: Path) -> tuple[str, bool, int, str]:
    relative_pdf = pdf_path.relative_to(VERIFY_DOWNLOADS)
    output_path = (OUTPUT_ROOT / relative_pdf).with_suffix(".txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and output_path.stat().st_size > 0:
        return (str(relative_pdf), True, 0, "skipped_existing")

    try:
        reader = PdfReader(str(pdf_path))
        text_parts: list[str] = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if not text:
            return (str(relative_pdf), False, 0, "empty_text")
        output_path.write_text(text + "\n", encoding="utf-8")
        return (str(relative_pdf), True, len(reader.pages), "extracted")
    except Exception as exc:  # pragma: no cover - batch robustness
        return (str(relative_pdf), False, 0, f"error:{type(exc).__name__}:{exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Florida verify PDFs into structured text files.")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker processes")
    args = parser.parse_args()

    pdf_paths = sorted(VERIFY_DOWNLOADS.rglob("*.pdf"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped_existing = 0
    empty_text = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(extract_pdf, path): path for path in pdf_paths}
        for future in as_completed(futures):
            _, ok, _, status = future.result()
            if status == "skipped_existing":
                skipped_existing += 1
            elif status == "extracted":
                extracted += 1
            elif status == "empty_text":
                empty_text += 1
            else:
                errors += 1

    print(
        f"pdfs_total={len(pdf_paths)}, extracted={extracted}, "
        f"skipped_existing={skipped_existing}, empty_text={empty_text}, errors={errors}"
    )


if __name__ == "__main__":
    main()
