---
name: state-court-opinion-normalization
description: Normalize state court opinion datasets into state/court/year/case/opinion.txt, repair missing text extraction when authoritative PDFs exist, and verify organized output against authoritative snapshots. Use when organizing more states, adapting the workflow to new source layouts, or auditing recovery and mapping accuracy.
---

# State Court Opinion Normalization

Use this skill when working on state court opinion datasets in this repository.

## Outcome

Produce or verify a normalized state tree:

```text
<state>/
  <court>/
    <court>_metadata.csv
    <year>/
      <case>/
        opinion.txt
```

Each retained case must have a real opinion text file. Never generate placeholder `opinion.txt` files.

## Files To Know

- `reorganize_data.py`
  California-specific organizer
- `reorganize_states.py`
  Main multi-state organizer
- `extract_florida_verify_text.py`
  Florida authoritative extraction helper
- `extract_verify_state_texts.py`
  Extraction helper for verify snapshots
- `verify-data/`
  Authoritative comparison snapshots when available

## Non-Negotiable Rules

1. The year folder is the opinion or release year.
2. A docket prefix like `23-xxxx` is not the year.
3. Prefer the opinion text header for year if it clearly states the opinion year.
4. Otherwise use a trustworthy opinion/release date field from metadata.
5. Only fall back to path-derived year when that path is known to represent opinion year.
6. Exclude records with no real local opinion text.
7. Distinguish row counts from unique-case counts during QA.

## Workflow

### 1. Intake the state

Before changing code, determine:

- authoritative CSV path
- local text source path
- whether PDFs must be extracted first
- court mapping rule
- case key rule
- opinion date field
- year derivation rule

If any of those are unclear, inspect the raw files before coding.

### 2. Decide whether the existing organizer fits

Use the current script structure if the state matches an existing pattern:

- CSV + flat text corpus indexed by basename
- CSV + nested text path derived from `pdf_local_path`
- CSV + authoritative `pdf_path`
- URL-derived translation/document id

If the state does not fit an existing pattern, add a dedicated organizer function rather than forcing a bad abstraction.

### 3. Resolve the text source correctly

Preferred matching order:

1. full relative `pdf_path`
2. `pdf_local_path`
3. stable document id from URL
4. basename only, if collisions are impossible

Do not match by basename when the dataset has filename collisions.

### 4. Derive the year correctly

Use this priority:

1. opinion text header year
2. opinion/release/filed date metadata
3. known-safe source path year

Examples from this repo:

- California: `Filed mm/dd/yy` in opinion text
- Florida: `release_date`
- Georgia: parsed opinion `date`, fallback source `year`
- Iowa: `filed_date`
- Colorado: `date`
- Louisiana: `published_date`
- Maine: `date_filed`
- Maryland: `filed_date`
- Massachusetts: `release_date`
- Montana: `YYYY MT n` in the opinion header, else `file_date`

Be careful with text parsing. Restrict header-based regexes to the top of the document so cited cases in the body do not contaminate the year.

### 5. Organize the output

For each retained record:

1. find the opinion text
2. compute court folder
3. compute year
4. compute case folder from the case key
5. copy the text to `opinion.txt`
6. add a metadata row

If two records collide on the same case folder name in one court/year, suffix the folder deterministically.

### 6. Verify internally

Check:

1. metadata rows equal case folders
2. case folders equal `opinion.txt` files
3. no placeholder opinions exist
4. folder year equals the correct opinion/release year source

### 7. Verify against authoritative data

If `verify-data/<state>/` exists:

1. compare organized rows to authoritative rows
2. compare organized unique cases to authoritative unique cases
3. separate organizer bugs from missing local text
4. explain every gap

Use the true case key for unique-case QA. Do not treat raw row count as case count unless the dataset is actually one-row-per-case.

## When To Repair Extraction

Repair missing extraction only when:

- authoritative PDFs exist locally, and
- the organized output is missing cases because the text corpus is incomplete

If the authoritative snapshot itself does not contain the PDF, report that as an upstream source gap, not an organizer bug.

## How To Work At Scale

For many states at once, separate work into four lanes:

1. intake and source mapping
2. PDF-to-text repair
3. organization
4. QA and authoritative verification

Recommended ownership:

- one owner for shared script integration
- one owner per batch of states for intake and verification
- extraction work can run independently from organizer refactors

Parallelize across states, not across the same write-heavy script block.

## Decision Rules For Refactoring

- Add a helper only after at least two states need the same behavior.
- Keep one-off state quirks inside that state's organizer function.
- If a helper changes year logic, re-audit every state that uses it.
- If a helper changes text matching, re-check collision risk.

## Deliverables For Each Completed State

Report:

1. source rows
2. organized rows
3. unique cases
4. skipped rows and why
5. whether authoritative verification passed
6. whether year-folder QA passed

Do not mark a state complete without explicit year-folder QA.
