# Master Plan: State Court Opinion Organization & Verification

## Scope

Organize **all** state court opinion data into the normalized directory structure, verify at 3 levels, and fix all gaps automatically. No state is considered "done" from prior work -- every state is processed and verified fresh.

## States In Scope (17)

| # | State | CSV Rows | Txt Files | Status |
|---|---|---|---|---|
| 1 | Colorado | ~2,019 | ~2,019 | Re-process from scratch |
| 2 | Florida | ~8,000+ | 2,012 | Re-process -- partial txt coverage |
| 3 | Georgia | 2,803 | 2,564 | Re-process -- txt in download/ not downloads/ |
| 4 | Iowa | ~9,400 | 9,493 | Re-process from scratch |
| 5 | Louisiana | 5,218 | 0 | **Extract PDFs first**, then organize |
| 6 | Maine | 1,139 | 0 | **Extract PDFs first**, then organize |
| 7 | Maryland | 9,849 | 0 | **Extract PDFs first**, then organize |
| 8 | Massachusetts | 19,389 | 0 | **Extract PDFs first**, then organize |
| 9 | Montana | 184 | 0 | **Extract PDFs first**, then organize |
| 10 | Nevada | 5,066 | 5,022 | New -- build organizer |
| 11 | New Hampshire | 5,289 | 5,216 | New -- build organizer (3jx/supervisory have 0 txt) |
| 12 | New Jersey | 20,262 | 20,077 | New -- build organizer |
| 13 | New Mexico | 33,207 | 30,819 | New -- build organizer |
| 14 | North Carolina | 37,877 | 37,768 | New -- build organizer |
| 15 | Pennsylvania | 1,000 | 482 | New -- build organizer, ~48% coverage |
| 16 | Rhode Island | 10,132 | 9,139 | New -- build organizer |
| 17 | South Carolina | 20,172 | 20,129 | New -- build organizer |
| 18 | Vermont | 11,310 | 0 | **Extract PDFs first**, then organize |

**Total: ~192,000+ CSV rows, ~144,000+ txt files available, 6 states need extraction**

## States Excluded

| State | Reason |
|---|---|
| Alaska | HTML-based data, not PDF/txt |
| California | Excluded per user request |
| Oregon | Txt files are page-level fragments (e.g., 20.txt, 54.txt per case), skipped |
| US Supreme Court | 0 txt files, CSV only |

## Locked-In Decisions

### 1. Data Paths

| Role | Path |
|---|---|
| Raw data (CSVs + PDFs) | `C:\Users\TRENDING PC\LegalAI-Scraper\<state>\` |
| Converted txt files | `C:\Users\TRENDING PC\LegalAI-Scraper\txt_output\<state>\` |
| Organized output | `C:\Users\TRENDING PC\LegalAI-Scraper\z-cleaning\clean-data\<state>\` |

Scripts will be updated to point at these actual paths. No data copying into clean-data.

### 2. Output Structure

```text
clean-data/
  <state>/
    <court_folder>/
      <court_folder>_metadata.csv
      <year>/
        <case_folder>/
          opinion.txt
```

### 3. Document Type Handling

Each document type gets its own separate court/sub-court folder:

- **Nevada**: `advance_opinions/`, `unpublished_orders/`
- **New Hampshire**: `opinions/`, `case_orders/`, `3jx_final_orders/`, `supervisory_orders/`
- **New Jersey**: `supreme/`, `published_appellate/`, `unpublished_appellate/`
- **Pennsylvania**: `opinions_supreme/`, `opinions_superior/`, `opinions_commonwealth/`, `opinions_disciplinaryboard/`, `aopc_web_public/`
- **South Carolina**: `published_supreme_court/`, `published_court_of_appeals/`, `unpublished_supreme_court/`, `unpublished_court_of_appeals/`

### 4. Year Derivation Rule (Non-Negotiable)

Priority order for every state:
1. Opinion text header year (if clearly stated in top lines)
2. Opinion/release/filed date metadata field
3. Known-safe source path year (fallback only)

Never use docket prefix (e.g., `23-xxxx`) as year.

### 5. Verification: 3 Levels

```
Level 1: Raw PDFs    (LegalAI-Scraper/<state>/downloads/)
Level 2: Txt Output  (LegalAI-Scraper/txt_output/<state>/)
Level 3: Organized   (clean-data/<state>/)
```

**Diff 1**: Level 1 vs Level 2 = PDFs that failed txt conversion
**Diff 2**: Level 2 vs Level 3 = txt files that failed to organize
**Diff 3**: Level 3 internal = metadata rows vs case folders vs opinion.txt files

Each state gets its own verification CSV report.

### 6. Gap Fixing

Fix everything automatically:
- Re-extract missing PDFs to txt (where PDFs exist but txt is missing)
- Fix organizer mapping bugs (where txt exists but was not organized)
- Report upstream source gaps separately (where no PDF exists at all)

### 7. Execution Strategy

Batch by batch:
1. Inspect CSVs for a group of states
2. Build/update organizers for that group
3. Run organization
4. Run 3-level verification
5. Fix gaps
6. Move to next batch

## Phase Plan

### Phase 1: CSV Inspection (All 17 States)

For each state, identify:
- CSV file location(s)
- All column names
- Case key field (unique identifier)
- Date field (opinion/release year source)
- Court mapping field or rule
- PDF path field (to match txt files)
- Txt file naming convention and matching strategy

### Phase 2: Update Existing States

Update `reorganize_states.py` for the 9 existing states (CO, FL, GA, IA, LA, ME, MD, MA, MT):
- Point at actual data paths (`LegalAI-Scraper/<state>/` and `txt_output/<state>/`)
- Do NOT assume prior output is correct -- re-run from scratch

### Phase 3: Build New State Organizers

Add organizer functions for 9 new states (NV, NH, NJ, NM, NC, PA, RI, SC, VT):
- Follow existing patterns where possible
- Add dedicated functions for unique layouts
- Each document type = separate folder

**Batch grouping by execution order:**

| Batch | States | Prerequisite | Pattern |
|---|---|---|---|
| 0 (Extract) | Louisiana, Maine, Maryland, Massachusetts, Montana, Vermont | pdf_to_txt.py | Must extract PDFs to txt before organizing |
| A | Colorado, Iowa, Nevada, Rhode Island | None (txt ready) | Hierarchical txt + pdf_local_path derivation |
| B | Florida, Georgia | None (txt ready) | Flat/year-month txt + basename/stem index |
| C | New Jersey, South Carolina | None (txt ready) | Court-type + flat `{case_no}.txt` |
| D | New Mexico, North Carolina | None (txt ready) | Court + pdf_id/item_id matching |
| E | New Hampshire | None (partial txt) | Multi-category + pdf_local_path derivation |
| F | Pennsylvania | None (partial txt) | Flat + `__` delimiter matching |
| G | Post-extraction | Batch 0 complete | Organize LA, ME, MD, MA, MT, VT |

### Phase 4: Build 3-Level Verification Script

Create `verify_pipeline.py` that:
1. Counts raw PDFs per state/court from `LegalAI-Scraper/<state>/downloads/`
2. Counts txt files per state/court from `txt_output/<state>/`
3. Counts organized opinion.txt and metadata rows from `clean-data/<state>/`
4. Computes diffs at each level
5. Outputs per-state CSV reports with:
   - `<state>_verification.csv` -- row-level detail
   - Missing at Level 2 (PDF exists, no txt)
   - Missing at Level 3 (txt exists, not organized)
   - Internal inconsistencies (metadata vs folders vs opinion.txt)

### Phase 5: Run Everything, Fix Gaps

1. Run all organizers
2. Run verification
3. Auto-fix:
   - Re-run `pdf_to_txt.py` for missing txt files
   - Fix organizer mapping bugs
   - Re-run organizers after fixes
4. Re-verify until clean

## Existing State Field Mappings (From Current Script)

| State | Case Key | Date Field | Date Format | Courts | Text Lookup |
|---|---|---|---|---|---|
| Colorado | `docket_number` | `date` | `%B %d, %Y` | 2: Supreme, Appeals | translation-id index |
| Florida | `case_no` | `release_date` | `%m/%d/%y` | 8: SC, 1-6 DCA, unknown | pdf_file stem or verify path |
| Georgia | `case_id` | `date` | `%B %d, %Y` | 1: Supreme | basename index |
| Iowa | `case_no` | `filed_date` | `%b %d, %Y` | 2: Supreme, Appeals | pdf_local_path derivation |
| Louisiana | text file stem | `published_date` | ISO datetime | 1: Supreme | basename index |
| Maine | `opinion_number` | `date_filed` | `%B %d, %Y` | 1: Supreme Judicial | basename index |
| Maryland | `docket_term` | `filed_date` | `%Y-%m-%d` | 2: Supreme, Appellate | basename index |
| Massachusetts | `docket_number` | `release_date` | `%Y-%m-%d` | 1: Appeals | basename index |
| Montana | `case_number` | `file_date` | ISO datetime | 1: Supreme | basename index |

## New State Field Mappings (Determined in Phase 1)

| State | Case Key | Date Field | Date Format | Courts | Text Lookup |
|---|---|---|---|---|---|
| Nevada | `case_number` | `opinion_date` (advance) / `order_date` (unpub) | `%b %d, %Y` | 2: advance_opinions, unpublished_orders | pdf_local_path .pdf->.txt |
| New Hampshire | `case_number` | `case_date` | `%Y-%m-%d` | 4: opinions, case_orders, 3jx_final_orders, supervisory_orders | pdf_local_path .pdf->.txt |
| New Jersey | `no` + `court` | `date` | `%B %d, %Y` (variable abbrev) | 3: supreme, published_appellate, unpublished_appellate | `{no}_{pdf_stem}.txt` in court/file/ |
| New Mexico | `item_id` | `publication_date` | `%m/%d/%Y` | 2: supreme_court, court_of_appeals | item_id regex from txt filename |
| North Carolina | pdf_id from `pdf_url` | `date` | `%B %d, %Y` | 3: supreme_court, court_of_appeals, business_court | pdf_id/VersionId from pdf_url to txt suffix |
| Pennsylvania | `pdf_file` basename after `__` | `date` | `%m/%d/%Y` (no zero-pad) | 5: opinions_supreme/superior/commonwealth/disciplinaryboard, aopc_web_public | Match on `__` suffix in flat dir |
| Rhode Island | `case_number` | `case_date` | `%A, %B %d, %Y` | 1: supreme_court | `{case_number}.txt` in year/case/ |
| South Carolina | `case_no` | `Date` | `%B %d, %Y` (ALL CAPS) | 4: pub/unpub x supreme/appeals | `{case_no}.txt` flat in court/PDF/ |
| Vermont | `Case Number` | `Date` | `%m/%d/%Y` | 7: supreme_court, civil, criminal, environmental, family, probate, unknown_court | PDF filename stem (irregular) |

## CRITICAL FINDINGS FROM CSV INSPECTION

### Txt Availability by State

**States with txt files ready to organize:**

| State | CSV Rows | txt Files | Coverage | Notes |
|---|---|---|---|---|
| Colorado | ~2,019 | ~2,019 | ~100% | translation-id flat files |
| Florida | ~8,000+ | 2,012 | ~25% | Only partial coverage |
| Georgia | 2,803 | 2,564 | ~91% | In `download/` not `downloads/` |
| Iowa | ~9,400 | 9,493 | ~100% | Hierarchical year/case structure |
| Nevada | 5,066 | 5,022 | ~99% | 44 missing in unpublished |
| New Hampshire | 5,289 | 5,216 | ~99% | 3jx + supervisory have 0 txt |
| New Jersey | 20,262 | 20,077 | ~99% | Flat in court/file/ dirs |
| New Mexico | 33,207 | 30,819 | ~93% | SC ~87%, CA ~99.9% |
| North Carolina | 37,877 | 37,768 | ~99.7% | 36,274 appellate + 1,494 biz |
| Pennsylvania | 1,000 | 482 | ~48% | Many PDFs not converted |
| Rhode Island | 10,132 | 9,139 | ~90% | year/case_number hierarchy |
| South Carolina | 20,172 | 20,129 | ~99.8% | Flat {case_no}.txt |

**States with NO txt files (must run PDF-to-text extraction):**

| State | CSV Rows | Action |
|---|---|---|
| Louisiana | 5,218 | Must run pdf_to_txt.py |
| Maine | 1,139 | Must run pdf_to_txt.py |
| Maryland | 9,849 | Must run pdf_to_txt.py |
| Massachusetts | 19,389 | Must run pdf_to_txt.py |
| Montana | 184 | Must run pdf_to_txt.py |
| Vermont | 11,310 | Must run pdf_to_txt.py (not in txt_output at all) |

### State-Specific Issues Found

1. **New Hampshire supervisory-orders CSV** has CSV parsing/quoting bugs (fields shift due to embedded commas)
2. **New Hampshire 3jx-final-orders** has `case_date` always empty -- must derive year from path
3. **North Carolina `docket` column** is always `","` (useless) -- must use `pdf_url` for unique key
4. **North Carolina** Supreme Court + Court of Appeals txt files share one directory (`appellate_court_opinions/file/`)
5. **Pennsylvania** has no structured docket/case-number column -- must extract from `pdf_file`
6. **Pennsylvania `aopc-web-public`** contains admin docs, not court opinions -- may need filtering
7. **South Carolina** CSV has typos: `descpiction`, `Donwload PDF path`
8. **Vermont** PDF filenames are highly irregular (no consistent naming pattern)
9. **Vermont** has no txt files at all -- needs full PDF-to-text extraction first
10. **Georgia** txt files are in `download/` (year/month/flat) not `downloads/`
11. **Louisiana** has duplicate rows (same case listed under both direct PDF link and listing page)
12. **Maryland** `filed_date` can contain annotations like `corrected 2026-03-06` after the date
13. **Florida** only ~2,012 txt files for ~8,000+ CSV rows across 8 courts

## Files That Will Be Created/Modified

| File | Action |
|---|---|
| `reorganize_states.py` | Modify -- update paths for existing 9 states, add 9 new state organizers |
| `verify_pipeline.py` | Create -- 3-level verification script |
| `PLAN.md` | This file |
| `<state>_verification.csv` | Create per state -- verification output |

## Risk Register

| Risk | Mitigation |
|---|---|
| Docket prefix used as year | Strict year derivation rule, opinion header priority |
| Txt filename collisions across courts | Match by full path, not basename alone |
| Multiple CSV rows for same case | Deduplication by case key |
| 6 states have 0 txt files | Run pdf_to_txt.py before organizing |
| Montana has 0 txt files | Must extract from PDFs first |
| Vermont has no per-court CSVs or txt | Use merged CSV with `Court` column, extract PDFs first |
| Pennsylvania has non-opinion content | Filter by court/opinion type in CSV |
| North Carolina has .zip files mixed with .txt | Filter to .txt only |
| Oregon excluded but may be wanted later | Documented as excluded, can add later |
| NH supervisory CSV has parsing bugs | Use per-category CSV, not master; handle quoting |
| NC Supreme/Appeals share txt directory | Discriminate by `c=1`/`c=2` in pdf_url |
| SC CSV column names are misspelled | Map `Donwload PDF path` -> pdf path, `descpiction` -> description |
| MD filed_date has annotations | Regex-extract just the date portion |
| LA has duplicate rows | Deduplicate by case key before organizing |
