import csv
import json
from pathlib import Path

# Paths
reports_path = Path("outputs/reports.csv")
clusters_path = Path("outputs/clusters.json")
output_path = Path("outputs/reports_with_id.csv")

# Load clusters.json
with open(clusters_path, "r", encoding="utf-8") as f:
    clusters = json.load(f)

# Build id-to-filename mapping
id_to_filename = {}
for cluster_ids in clusters.values():
    for id_ in cluster_ids:
        id_to_filename[id_] = None  # Will fill in below

# Read all filenames from reports.csv
with open(reports_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    filenames = [row["filename"] for row in rows]

# Match ids to filenames using rules
filename_to_id = {}
for id_ in id_to_filename:
    for filename in filenames:
        stem = Path(filename).stem
        if stem == id_ or filename.startswith(id_) or id_ in filename:
            filename_to_id[filename] = id_
            break

# Add id column to reports.csv
with open(output_path, "w", encoding="utf-8", newline="") as f:
    fieldnames = ["id"] + reader.fieldnames
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        row_id = filename_to_id.get(row["filename"], "")
        row_out = {"id": row_id}
        row_out.update(row)
        writer.writerow(row_out)

print(f"Done. Output written to {output_path}")
