# Screenshot Classification & Clustering Pipeline (PRD)

## Overview

A small, production-ready Python pipeline to process mobile app screenshots, extract screen headings (Tamil + English), classify and cluster screens. All data is stored locally for easy testing and reproducibility. The pipeline is modular, easy to run, and requires no database or cloud setup.

## Goals

- Ingest a folder of mobile app screenshots (JPG, various resolutions)
- Extract screen headings (Tamil + English) using OCR
- Classify screenshots into canonical "screen" categories (rule-based + fuzzy match)
- Group uncertain/remaining screenshots by visual similarity (CLIP embeddings + clustering)
- Output results as local CSV and JSON files
- Arrange screenshots into cluster subfolders using `arrange_screenshots.py`
- Provide a minimal Flask web UI for reviewing and adjusting cluster labels and merging clusters

## Input

- Folder of screenshots (JPG, any resolution)
- Screenshots may have overlays/notifications covering the header

## Output

1. `reports.csv`:
   - Columns: id, filename, ocr_text, ocr_confidence, predicted_screen_id, screen_confidence, cluster_id
2. `clusters.json`:
   - Format: JSON object mapping `cluster_id` (string) to a list of `ids` (strings or numbers).
   - Example:
     ```json
     {
       "clip_0": [
         "28d7eb3a67da9198eeb2f012a5fb873ca5ddc3d6",
         "2b49a421bdec82b8b3534ffe19c5875ec699fde2"
       ],
       "clip_1": [
         "022df92e6e87dc46889f850273a5a8059a0f5b4d",
         "03e873a68eb6c2e6dceb9b332db5de055eb9548f"
       ]
     }
     ```
3. Arranged screenshot folders:
   - Produced by `arrange_screenshots.py`:
     - `<output_dir>/<cluster_id>/*` — files for that cluster
     - `<output_dir>/_unassigned/*` — input images not matched to any id (copied/moved here)
4. Minimal Flask web UI (`/review`):
   - Shows clusters with sample images and extracted headings
   - Allows assigning or editing canonical `screen_id` for each cluster
   - Allows merging clusters and updating labels (writes changes to CSV & JSON)

## Autonomous Image Categorization Pipeline

### New Addition: Fully Autonomous Pipeline

A new `run_pipeline.py` script provides a fully autonomous image categorization pipeline that:

- Takes only the Firebase export JSON as input
- Downloads all images from Firebase Storage URLs
- Performs OCR on downloaded images
- Categorizes images using intelligent heuristics
- Produces final JSON with all records categorized
- Requires no manual intervention or existing OCR data

#### Usage
```bash
python run_pipeline.py [--input INPUT_FILE] [--output OUTPUT_FILE] [--verbose] [--dry-run]
```

#### Features
- **Single Source of Truth**: Uses only the provided JSON file
- **Autonomous Downloads**: Downloads images to `input_screenshots/` directory
- **Multi-Strategy Categorization**: OCR text analysis, filename patterns, metadata analysis
- **Robust Error Handling**: Defensive programming with comprehensive logging
- **Complete Coverage**: Every record guaranteed to have a category field

## Pipeline Stages

1. **Preprocessing & Header Detection**
   - Load each screenshot, auto-detect and crop the likely header region (top ~15-20% of image, tunable)
   - Resize/correct orientation if needed
   - Save cropped header for OCR
2. **OCR Extraction**
   - Use Tesseract (`tam+eng`) to extract text from header crop
   - Capture OCR confidence score
   - Optionally support other OCR APIs (pluggable)
3. **Text Normalization**
   - Clean up OCR output: remove noise, normalize whitespace, fix common OCR errors, lowercase, strip symbols
   - Optionally transliterate Tamil to Latin for matching
4. **Screen Classification**
   - Match normalized text against a `KNOWN_SCREENS` dictionary (exact match first, then fuzzy match using rapidfuzz)
   - Assign `predicted_screen_id` and confidence score (e.g., 1.0 for exact, <1.0 for fuzzy)
   - If match confidence is low or OCR fails, mark as "uncertain"
5. **Visual Clustering**
   - For uncertain/failed OCR: compute CLIP embeddings for the full screenshot
   - Cluster visually similar images using AgglomerativeClustering (or faiss for large sets)
   - Assign `cluster_id` to each image
6. **Output Generation**
   - Write `reports.csv` (all images, with all columns)
   - Write `clusters.json` (cluster_id -> list of ids)
   - Arrange screenshots into cluster folders using `arrange_screenshots.py`
     - See Section 14 Appendix for details
7. **Review UI**
   - Minimal Flask app at `/review`
   - Shows clusters with sample images and extracted headings
   - Allows user to assign/edit canonical `screen_id` for each cluster
   - Allows merging clusters and updating labels
   - All changes update `reports.csv` and `clusters.json` in real time

## Arranger Script (`arrange_screenshots.py`)

- **Purpose:** Physically arranges screenshots into cluster subfolders using `clusters.json`.
- **Input contract:**
  - `clusters.json`: JSON object mapping `cluster_id` -> list of ids (strings or numbers).
  - `reports.csv` (optional): CSV with columns `id` and `filename` (case-insensitive).
  - `input_dir`: Folder containing screenshots (top-level only).
- **Output contract:**
  - `<output_dir>/<cluster_id>/*` — files for that cluster
  - `<output_dir>/_unassigned/*` — input images not matched to any id
- **Matching rules (priority order):**
  1. If `reports.csv` maps id -> filename, check `input_dir/filename` exactly.
  2. filename stem == id
  3. filename startswith id
  4. id in filename
- **Allowed extensions:** Defaults to `jpg,png,jpeg` (configurable via `--ext`).
- **Multiple matches:** All matching files for an id are placed in the cluster folder.
- **Unassigned files:** Any input image not assigned to a cluster is placed in `_unassigned`.
- **No files are deleted except when using `--move` (which moves originals).**
- **CLI usage:**
  - Copy mode (default):  
    `python arrange_screenshots.py <input_dir> <clusters.json> <output_dir>`
  - Move mode:  
    `python arrange_screenshots.py <input_dir> <clusters.json> <output_dir> --move`
  - With reports mapping:  
    `python arrange_screenshots.py <input_dir> <clusters.json> <output_dir> --reports <reports.csv>`
  - Dry-run:  
    `python arrange_screenshots.py <input_dir> <clusters.json> <output_dir> --dry-run`
  - Verbose logging:  
    `python arrange_screenshots.py <input_dir> <clusters.json> <output_dir> --verbose`
- **Exit codes:**
  - 2: Input directory or clusters.json missing, or reports.csv missing/invalid.
- **Logging & summary:** Prints clusters processed, total assigned files, unassigned folder path, number of missing ids, and up to 10 example missing ids.

## Tech Stack & Libraries

- Python 3.10+
- opencv-python (image processing)
- pillow (image I/O)
- pytesseract (OCR; Tesseract must be installed separately)
- rapidfuzz (fuzzy text matching)
- transformers (CLIP: `openai/clip-vit-base-patch32` for embeddings)
- torch (for CLIP)
- scikit-learn (AgglomerativeClustering) or faiss (clustering)
- Flask (minimal web UI)
- pandas (CSV handling)
- **arrange_screenshots.py:** Python stdlib only (no extra dependencies)

## How to Run (Arranger Script)

- Copy mode (default):  
  `python arrange_screenshots.py ./screenshots ./clusters.json ./arranged_output`
- Move mode:  
  `python arrange_screenshots.py ./screenshots ./clusters.json ./arranged_output --move`
- With reports mapping:  
  `python arrange_screenshots.py ./screenshots ./clusters.json ./arranged_output --reports ./reports.csv`
- Dry-run:  
  `python arrange_screenshots.py ./screenshots ./clusters.json ./arranged_output --dry-run`
- Verbose logging:  
  `python arrange_screenshots.py ./screenshots ./clusters.json ./arranged_output --verbose`

## Acceptance Criteria

- Given a `clusters.json` mapping 100 ids and an input folder, running the script should place all matching files into cluster folders and put unmatched files into `_unassigned`.
- All CLI flags, matching rules, and output structure must match the documented behavior.
- No files are deleted except when using `--move`.

# Section 14 — Appendix: Arrange script notes & behaviour

1. Purpose

   - Provide one-command local arrangement of screenshots into folders using `clusters.json`.

2. Matching rules used (fall-through):
   a. If a `reports.csv` is supplied with columns `id, filename`, script will look for exact filename in input folder.
   b. Otherwise the script searches the input folder for files matching the cluster id using:

   - filename stem == id (strong match)
   - filename startswith id (common for hashed filenames)
   - id in filename (fallback)
     c. Allowed extensions default to jpg,png,jpeg (customizable via `--ext`).

3. Output structure

   - `<output_dir>/<cluster_id>/*` — files for that cluster
   - `<output_dir>/_unassigned/*` — input images not matched to any id (copied/moved here)
   - Script prints a summary with counts and missing ids.

4. Typical single-command usage (copy mode):

   - `python arrange_screenshots.py ./screenshots /mnt/data/clusters.json ./arranged_output`

5. Typical single-command usage (move mode):

   - `python arrange_screenshots.py ./screenshots /mnt/data/clusters.json ./arranged_output --move`

6. Dry-run & troubleshooting:

   - To preview actions without changing files: add `--dry-run`.
   - To get more logging: add `--verbose`.

7. CSV mapping (reports.csv)

   - If you have a `reports.csv` (exported by your pipeline) that maps cluster ids (hashes) to real filenames, pass it with `--reports /path/to/reports.csv`. CSV must contain at least two columns: `id` and `filename` (case-insensitive).

8. Edge cases

   - If multiple files match the same id, **all** matches are placed in the cluster folder (useful when screenshots were stored with different suffixes).
   - If you prefer only the first match only, you can edit the script (search behavior in `find_matches_for_id`) — quick change: return only the first found match.

9. Note about your clusters.json

   - This script expects the format `cluster_id -> [id1, id2, ...]`. I used the `clusters.json` you uploaded as input during development. :contentReference[oaicite:1]{index=1}

10. No external dependencies
    - The script uses only Python stdlib (Pathlib / shutil / argparse / json / csv), so it should run with Python 3.8+ out of the box.
