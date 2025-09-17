# Quick Start: Screenshot Pipeline

## 1. Validate and Fix Reports

```sh
python scripts/validate_and_fix_reports.py --input-csv outputs/reports.csv --output-csv outputs/classified_reports.csv --images-root input_screenshots
```

- Adds deterministic id (sha1 of full image path)
- Ensures cluster_id exists
- Coerces confidences to float
- Handles missing/duplicate filenames

## 2. Generate CLIP Clusters

```sh
python scripts/generate_clusters_json.py --fixed-csv outputs/classified_reports.csv --images-root input_screenshots --clusters-json outputs/clusters.json
```

- Computes CLIP embeddings for uncertain screenshots (screen_confidence < 0.8)
- Clusters them deterministically
- Assigns cluster ids: clip_0, clip_1, ...
- Writes sorted clusters.json

## 3. Review and Merge Clusters (Flask UI)

```sh
python flask_app/review_app.py --csv outputs/classified_reports.csv --clusters-json outputs/clusters.json --images-root input_screenshots
```

- Open http://127.0.0.1:5000/ in your browser
- Label clusters, merge as needed
- Changes are atomic and robust

## 4. Utility: CLIP Cluster

```sh
python scripts/clip_cluster.py --input-csv outputs/classified_reports.csv --images-root input_screenshots --output-csv outputs/clip_clustered.csv
```

- Computes CLIP clusters for any CSV

## 5. Arrange Screenshots into Cluster Folders

```sh
python scripts/arrange_screenshots.py input_screenshots outputs/clusters.json outputs/arranged_screenshots --verbose
```

- Copies screenshots into cluster subfolders using the hardcoded mapping from reports.csv
- Output is placed in `outputs/arranged_screenshots` with clusters as subfolders
- Use `--move` to move files instead of copying

## 6. Arrange Screenshots by Header Content (Alternative)

```sh
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers --min-group-size 2 --verbose
```

- Groups screenshots based on their header content (OCR text) instead of CLIP clusters
- Uses a problem-focused taxonomy for final categorization via `config/categories.json` and `pipeline/mapping_rules.py`
- Useful for organizing by issue type (e.g., connectivity, authentication, performance, UI/UX)
- Output is placed in `outputs/arranged_by_headers` with content-based subfolders

## Next Steps

- After reviewing clusters, use the labeled/merged CSV and clusters.json for downstream tasks.
- All scripts are idempotent and robust to missing/duplicate files.
- For troubleshooting, check logs and ensure images are accessible.
