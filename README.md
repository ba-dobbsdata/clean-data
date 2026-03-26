# State Court Opinion Normalization

This repository contains the scripts, workflow, and QA process for normalizing state court opinion datasets into a single directory shape:

```text
<state>/
  <court>/
    <court>_metadata.csv
    <year>/
      <case>/
        opinion.txt
```

The raw data is intentionally not part of the repository because it is large and state-specific. The repo should keep only the reusable scripts, documentation, and lightweight QA artifacts.

## Goal

For each state, convert whatever raw layout exists into:

1. State-level folder
2. Court-level folders
3. Court-level metadata CSV
4. Year-level folders
5. Case-level folders
6. `opinion.txt` in every retained case folder

Only retain records with a real local opinion text source. Do not create placeholder `opinion.txt` files for missing opinions.

## Core Rule: How Year Is Assigned

The year folder must reflect the opinion or release year, not the docket prefix and not the case filing year unless that filing year is explicitly the opinion/release date source for that dataset.

Priority order:

1. Use the opinion text itself if the header contains the opinion year.
2. Otherwise use a trustworthy opinion/release date field from metadata.
3. Only use a storage-path year or source-folder year as a fallback if it is known to represent the opinion/release year.

Never assume a case number like `23-xxxx` means the case belongs in `2023`.

## Current Scripts

- `reorganize_data.py`
  California-specific organizer
- `reorganize_states.py`
  Multi-state organizer for the currently supported non-California states
- `extract_florida_verify_text.py`
  Florida authoritative PDF-to-text extraction helper
- `extract_verify_state_texts.py`
  Verify-data extraction helper for states whose local text corpus is incomplete

## Standard Workflow For A New State

### 1. Inventory the source

Identify:

- the authoritative metadata CSV or CSVs
- the real opinion-bearing source files
- whether text already exists locally or must be extracted from PDFs
- the correct court split
- the correct unique case key
- the correct opinion/release date field

Questions to answer before coding:

- Is the current source row-based, case-folder-based, or document-based?
- Does one source row equal one opinion, or can several rows point to the same underlying PDF?
- Are there duplicate wrappers, daily-order rows, summary rows, or other noisy entries?
- Is there a better authoritative snapshot under `verify-data/`?

### 2. Define the case key

Use the real source identifier for that dataset. Examples already encountered:

- Florida: `court + case_no`
- Georgia: `case_id`
- Iowa: `court + case_no`
- Colorado: `court + docket_number`
- Montana: `case_number`
- California: source case folder name within court

Do not use the folder name blindly unless the dataset really uses it as the case identifier.

### 3. Define the opinion year rule

For each state, document which source determines the year:

- opinion text header
- release date field
- filed date field
- file date field

Write this down before organizing the state. This is the highest-risk mapping decision.

### 4. Build or repair the text corpus

If local `*.txt` opinions are incomplete:

1. find the authoritative PDF snapshot
2. extract text into a deterministic local text tree
3. match text back to metadata using a stable identifier such as `pdf_path`, `pdf_local_path`, `pdf_file`, or a derived translation id

If no real text exists, exclude the record.

### 5. Organize the state output

For each retained record:

1. resolve the source text file
2. derive the correct court folder
3. derive the correct opinion year
4. derive the case folder from the case key
5. copy the source text to `opinion.txt`
6. write the row into that court's metadata CSV

If multiple records in the same court/year want the same case folder name, suffix the folder deterministically.

### 6. Run QA

Every state needs these checks:

1. `metadata rows == case folders == opinion.txt files`
2. `year folder == opinion/release year source`
3. no placeholder `opinion.txt`
4. no organized-only records that do not exist in the source snapshot
5. missing records are explained by missing local text or missing PDFs, not bad mapping

### 7. Verify against authoritative data

When `verify-data/` exists:

1. compare organized output to the authoritative snapshot
2. distinguish source incompleteness from organizer bugs
3. compare by the true case key, not just row counts
4. watch for row-level duplicates pointing to the same PDF

Useful categories:

- authoritative rows
- authoritative unique cases
- PDF-backed authoritative records
- organized rows
- organized unique cases
- missing because text is absent
- extra organized rows
- field mismatches on overlapping rows

## State-Specific Adaptation Checklist

When adding a new state to `reorganize_states.py`, define these items first:

- state root path
- organizer function name
- metadata CSV path or paths
- text root and text lookup strategy
- court mapping rule
- case key rule
- opinion date rule
- year derivation rule
- duplicate handling rule
- source fields to preserve in metadata

Common text lookup strategies:

- by `pdf_local_path` stem
- by `pdf_file` stem
- by full relative `pdf_path`
- by a translation/document id embedded in a URL

## Scaling To Many States

For a large batch, do not treat all states as identical. Split the work like this:

### Track A: State intake

For each state, record:

- authoritative source location
- local text availability
- case key
- opinion year source
- expected court structure
- known risks

This can be done in parallel because it is read-only.

### Track B: Extraction repair

Only for states with missing local text:

- extract missing PDFs to text
- store extracted text in a stable, reusable location
- do not reorganize until text coverage is acceptable

### Track C: Organization

Group states by similarity:

- one-off state script
- common CSV + flat text layout
- common nested path layout
- translation-id mapping layout

Refactor shared helpers only after at least two states need the same logic.

### Track D: QA and verification

Run verification independently per state:

- row-level counts
- unique-case counts
- opinion year correctness
- authoritative comparison

Do not merge a state into the “done” set until the QA notes explain every gap.

## Recommended Way To Divide Work

If multiple agents or engineers are working at once:

1. one person owns the shared script integration
2. each other person owns a disjoint set of states
3. each state owner prepares a short intake note before editing code
4. extraction work and verification work can run in parallel with organization work
5. shared helpers should be merged carefully because they affect all states

Safe parallelization:

- inventory per state
- extraction per state
- verification per state

Avoid parallel edits to the same shared organizer file unless one person is responsible for final integration.

## Known Failure Modes

- using docket prefixes as years
- using case filing year instead of opinion/release year
- trusting `pdf_path` literally when the authoritative snapshot moved files
- treating noisy wrapper rows as separate cases
- matching text by filename only when filenames collide
- creating placeholder opinions for missing texts
- mixing row counts with unique-case counts

## Minimum Definition Of Done For A State

A state is done only when:

1. every retained case folder contains a real `opinion.txt`
2. the court metadata CSV exists for every court
3. the year folders reflect the correct opinion/release year source
4. counts reconcile internally
5. differences from the authoritative source are quantified and explained

## Suggested Git Layout

Keep in git:

- scripts
- `README.md`
- `SKILL.md`
- optional QA notes or lightweight CSV summaries

Ignore:

- raw downloaded PDFs
- extracted text corpora
- reorganized data trees
- large archives and zips

If needed, add a repo-level `.gitignore` that excludes state data directories and extracted text output.
