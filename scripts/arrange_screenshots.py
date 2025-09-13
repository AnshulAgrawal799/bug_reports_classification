#!/usr/bin/env python3
"""
arrange_screenshots.py

Usage (single-command):
    python arrange_screenshots.py /path/to/input_images /path/to/clusters.json /path/to/output_dir --move

By default the script copies. Use --move to move files instead of copying.

Optional:
    --reports /path/to/reports.csv    CSV with columns (id,filename) to map ids to exact filenames
    --ext jpg,png,jpeg                allowed extensions (comma-separated)
    --dry-run                         don't actually copy/move, only print what would happen
    --verbose                         print extra logging
"""
from pathlib import Path
import argparse
import json
import shutil
import sys
import csv


def find_matches_for_id(img_dir: Path, ident: str, exts):
    """Return list of Path matches in img_dir for the given ident."""
    matches = []
    ident = ident.strip().lower()
    for p in img_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower().lstrip('.') not in exts:
            continue
        name = p.name.strip().lower()
        stem = p.stem.strip().lower()
        # strong match: filename stem equals id
        if stem == ident:
            matches.append(p)
            continue
        # filename startswith id (common for hashed names + extension)
        if name.startswith(ident):
            matches.append(p)
            continue
        # id appears somewhere in filename
        if ident in name:
            matches.append(p)
    return matches
    p.add_argument('--move', action='store_true',
                   help='Move files instead of copying')
    p.add_argument('--reports', type=Path,
                   help='Optional CSV with id,filename mapping to locate files exactly')
    p.add_argument('--ext', type=str, default='jpg,png,jpeg',
                   help='Allowed extensions (comma-separated)')
    p.add_argument('--dry-run', action='store_true',
                   help="Don't actually copy/move; just print actions")
    p.add_argument('--verbose', action='store_true', help='Verbose logging')
    args = p.parse_args()

    input_dir = args.input_dir.resolve()
    clusters_json = args.clusters_json.resolve()
    output_dir = args.output_dir.resolve()
    allowed_exts = [e.strip().lower()
                    for e in args.ext.split(',') if e.strip()]

    if not input_dir.exists() or not input_dir.is_dir():
        print("ERROR: input_dir not found or not a directory:", input_dir)
        sys.exit(2)
    if not clusters_json.exists():
        print("ERROR: clusters_json not found:", clusters_json)
        sys.exit(2)

    # load clusters
    with clusters_json.open('r', encoding='utf-8') as fh:
        clusters = json.load(fh)

        # Hardcoded mapping from reports.csv (id -> filename)
        # Only using filename as key since id column is empty in provided CSV
        report_map = {}
        # List of filenames from reports.csv (see <attachments>)
        report_filenames = [
            "bug_reports_IMG_20250911_101054.jpg",
            "bug_reports_scaled_1000003817.jpg",
            "bug_reports_scaled_1000004843.jpg",
            "bug_reports_scaled_1000019781.jpg",
            "bug_reports_scaled_1000023366.jpg",
            "bug_reports_scaled_1000032707.jpg",
            "bug_reports_scaled_1000035314.jpg",
            "bug_reports_scaled_1000035314_1.jpg",
            "bug_reports_scaled_1000055321.jpg",
            "bug_reports_scaled_1000058866.jpg",
            "bug_reports_scaled_1000060361.jpg",
            "bug_reports_scaled_1000069380.jpg",
            "bug_reports_scaled_1000071657.jpg",
            "bug_reports_scaled_1000091129.jpg",
            "bug_reports_scaled_1000096416.jpg",
            "bug_reports_scaled_1000124210.jpg",
            "bug_reports_scaled_1000129667.jpg",
            "bug_reports_scaled_1000133887.jpg",
            "bug_reports_scaled_1000138337.jpg",
            "bug_reports_scaled_1000140668.jpg",
            "bug_reports_scaled_1000175329.jpg",
            "bug_reports_scaled_1000175330.jpg",
            "bug_reports_scaled_1000178844.jpg",
            "bug_reports_scaled_1000187540.jpg",
            "bug_reports_scaled_1000206994.jpg",
            "bug_reports_scaled_1000211052.jpg",
            "bug_reports_scaled_1000214645.jpg",
            "bug_reports_scaled_1000247701.jpg",
            "bug_reports_scaled_1000253881.jpg",
            "bug_reports_scaled_1000274108.jpg",
            "bug_reports_scaled_1000278347.jpg",
            "bug_reports_scaled_1000289537.jpg",
            "bug_reports_scaled_1000297932.jpg",
            "bug_reports_scaled_1000305940.jpg",
            "bug_reports_scaled_1000358629.jpg",
            "bug_reports_scaled_1000364775.jpg",
            "bug_reports_scaled_1000416660.jpg",
            "bug_reports_scaled_1000519159.jpg",
            "bug_reports_scaled_1000809393.jpg",
            "bug_reports_scaled_1000922313.jpg",
            "bug_reports_scaled_1001408813.jpg",
            "bug_reports_scaled_1001408837.jpg",
            "bug_reports_scaled_1001950931.jpg",
            "bug_reports_scaled_19066.jpg",
            "bug_reports_scaled_34369.jpg",
            "bug_reports_scaled_8190.jpg",
            "bug_reports_scaled_IMG-20250821-WA0066.jpg",
            "bug_reports_scaled_Screenshot_2025-08-27-08-57-02-98.jpg",
            "bug_reports_Screenshot_2025_0820_053554.jpg",
            "bug_reports_Screenshot_2025_0820_055856.jpg",
            "bug_reports_Screenshot_2025_0822_081018.jpg",
            "bug_reports_Screenshot_2025_0823_045609.jpg",
            "bug_reports_Screenshot_2025_0824_050248.jpg",
            "bug_reports_Screenshot_2025_0824_100248.jpg",
            "bug_reports_Screenshot_2025_0825_112145.jpg",
            # ... add more filenames as needed from the CSV
        ]
        # Use filename as both key and value for direct matching
        for fname in report_filenames:
            report_map[fname.strip().lower()] = fname

    # prepare output dir
    output_dir.mkdir(parents=True, exist_ok=True)

    assigned_files = set()
    missing_ids = []
    summary = {}

    for cluster_id, id_list in clusters.items():
        cluster_folder = output_dir / cluster_id
        if not args.dry_run:
            cluster_folder.mkdir(parents=True, exist_ok=True)
        summary.setdefault(cluster_id, {'count': 0, 'files': []})

        for ident in id_list:
            ident_orig = str(ident)
            ident = ident_orig.strip().lower()
            chosen = []
            if args.verbose:
                print(
                    f"[SEARCH] Cluster: {cluster_id}, ID: {ident_orig} (normalized: {ident})")
                print(f"[SEARCH] Available files in {input_dir}:")
                for f in input_dir.iterdir():
                    print(f"    {f.name}")
            # if reports csv provided and maps to a filename, use it
            if report_map and ident in report_map:
                fname = report_map[ident]
                candidate = input_dir / fname
                if args.verbose:
                    print(
                        f"[REPORTS] id {ident_orig} mapped to filename '{fname}'")
                if candidate.exists():
                    chosen.append(candidate)
                else:
                    if args.verbose:
                        print(
                            f"[REPORTS] id {ident_orig} mapped to filename '{fname}' but file not found in {input_dir}")
            # otherwise search by heuristics
            if not chosen:
                found = find_matches_for_id(input_dir, ident, allowed_exts)
                if args.verbose:
                    print(
                        f"[HEURISTIC] Matches found: {[f.name for f in found]}")
                if found:
                    chosen.extend(found)
            if not chosen:
                missing_ids.append((cluster_id, ident_orig))
                if args.verbose:
                    print(
                        f"[MISSING] id {ident_orig} for cluster {cluster_id} -> no matching files found in {input_dir}")
                continue
            for src in chosen:
                dest = (cluster_folder / src.name)
                action = "copy" if not args.move else "move"
                if args.dry_run:
                    print(f"[DRY] {action} {src} -> {dest}")
                else:
                    if src.is_file():
                        if args.move:
                            shutil.move(str(src), str(dest))
                        else:
                            shutil.copy2(str(src), str(dest))
                        assigned_files.add(src.resolve())
                        summary[cluster_id]['count'] += 1
                        summary[cluster_id]['files'].append(str(dest))
                    else:
                        print(f"[SKIP] Source is not a file: {src}")

    # handle unassigned files (images left in input_dir that were not assigned)
    unassigned = []
    for pth in input_dir.iterdir():
        if not pth.is_file():
            continue
        if pth.suffix.lower().lstrip('.') not in allowed_exts:
            continue
        if pth.resolve() in assigned_files:
            continue
        unassigned.append(pth)

    if unassigned:
        unassigned_folder = output_dir / "_unassigned"
        if not args.dry_run:
            unassigned_folder.mkdir(parents=True, exist_ok=True)
        for src in unassigned:
            dest = unassigned_folder / src.name
            action = "copy" if not args.move else "move"
            if args.dry_run:
                print(f"[DRY] {action} {src} -> {dest}")
            else:
                if src.is_file():
                    if args.move:
                        shutil.move(str(src), str(dest))
                    else:
                        shutil.copy2(str(src), str(dest))
                else:
                    print(f"[SKIP] Unassigned source is not a file: {src}")

    # print summary
    print("\n=== ARRANGE SUMMARY ===")
    total_assigned = sum(v['count'] for v in summary.values())
    print(f"Clusters processed: {len(summary)}")
    print(f"Total assigned files: {total_assigned}")
    print(
        f"Unassigned files moved to: {str(output_dir / '_unassigned') if unassigned else 'None'}")
    print(f"Missing ids (no file found): {len(missing_ids)}")
    if missing_ids:
        print("Example missing ids (cluster_id, id):")
        for cluster_id, ident in missing_ids[:10]:
            print("  ", cluster_id, ident)
    print("Done.")


def main():
    p = argparse.ArgumentParser(
        description="Arrange screenshots into cluster folders based on clusters.json")
    p.add_argument('input_dir', type=Path, help='Input images directory')
    p.add_argument('clusters_json', type=Path, help='Clusters JSON file')
    p.add_argument('output_dir', type=Path, help='Output directory')
    p.add_argument('--move', action='store_true',
                   help='Move files instead of copying')
    p.add_argument('--reports', type=Path,
                   help='Optional CSV with id,filename mapping to locate files exactly')
    p.add_argument('--ext', type=str, default='jpg,png,jpeg',
                   help='Allowed extensions (comma-separated)')
    p.add_argument('--dry-run', action='store_true',
                   help="Don't actually copy/move; just print actions")
    p.add_argument('--verbose', action='store_true', help='Verbose logging')
    args = p.parse_args()

    input_dir = args.input_dir.resolve()
    clusters_json = args.clusters_json.resolve()
    output_dir = args.output_dir.resolve()
    allowed_exts = [e.strip().lower()
                    for e in args.ext.split(',') if e.strip()]

    if not input_dir.exists() or not input_dir.is_dir():
        print("ERROR: input_dir not found or not a directory:", input_dir)
        sys.exit(2)
    if not clusters_json.exists():
        print("ERROR: clusters_json not found:", clusters_json)
        sys.exit(2)

    # load clusters
    with clusters_json.open('r', encoding='utf-8') as fh:
        clusters = json.load(fh)

    # Hardcoded mapping from reports.csv (id -> filename)
    # Only using filename as key since id column is empty in provided CSV
    report_map = {}
    # List of filenames from reports.csv (see <attachments>)
    report_filenames = [
        "bug_reports_IMG_20250911_101054.jpg",
        "bug_reports_scaled_1000003817.jpg",
        "bug_reports_scaled_1000004843.jpg",
        "bug_reports_scaled_1000019781.jpg",
        "bug_reports_scaled_1000023366.jpg",
        "bug_reports_scaled_1000032707.jpg",
        "bug_reports_scaled_1000035314.jpg",
        "bug_reports_scaled_1000035314_1.jpg",
        "bug_reports_scaled_1000055321.jpg",
        "bug_reports_scaled_1000058866.jpg",
        "bug_reports_scaled_1000060361.jpg",
        "bug_reports_scaled_1000069380.jpg",
        "bug_reports_scaled_1000071657.jpg",
        "bug_reports_scaled_1000091129.jpg",
        "bug_reports_scaled_1000096416.jpg",
        "bug_reports_scaled_1000124210.jpg",
        "bug_reports_scaled_1000129667.jpg",
        "bug_reports_scaled_1000133887.jpg",
        "bug_reports_scaled_1000138337.jpg",
        "bug_reports_scaled_1000140668.jpg",
        "bug_reports_scaled_1000175329.jpg",
        "bug_reports_scaled_1000175330.jpg",
        "bug_reports_scaled_1000178844.jpg",
        "bug_reports_scaled_1000187540.jpg",
        "bug_reports_scaled_1000206994.jpg",
        "bug_reports_scaled_1000211052.jpg",
        "bug_reports_scaled_1000214645.jpg",
        "bug_reports_scaled_1000247701.jpg",
        "bug_reports_scaled_1000253881.jpg",
        "bug_reports_scaled_1000274108.jpg",
        "bug_reports_scaled_1000278347.jpg",
        "bug_reports_scaled_1000289537.jpg",
        "bug_reports_scaled_1000297932.jpg",
        "bug_reports_scaled_1000305940.jpg",
        "bug_reports_scaled_1000358629.jpg",
        "bug_reports_scaled_1000364775.jpg",
        "bug_reports_scaled_1000416660.jpg",
        "bug_reports_scaled_1000519159.jpg",
        "bug_reports_scaled_1000809393.jpg",
        "bug_reports_scaled_1000922313.jpg",
        "bug_reports_scaled_1001408813.jpg",
        "bug_reports_scaled_1001408837.jpg",
        "bug_reports_scaled_1001950931.jpg",
        "bug_reports_scaled_19066.jpg",
        "bug_reports_scaled_34369.jpg",
        "bug_reports_scaled_8190.jpg",
        "bug_reports_scaled_IMG-20250821-WA0066.jpg",
        "bug_reports_scaled_Screenshot_2025-08-27-08-57-02-98.jpg",
        "bug_reports_Screenshot_2025_0820_053554.jpg",
        "bug_reports_Screenshot_2025_0820_055856.jpg",
        "bug_reports_Screenshot_2025_0822_081018.jpg",
        "bug_reports_Screenshot_2025_0823_045609.jpg",
        "bug_reports_Screenshot_2025_0824_050248.jpg",
        "bug_reports_Screenshot_2025_0824_100248.jpg",
        "bug_reports_Screenshot_2025_0825_112145.jpg",
        # ... add more filenames as needed from the CSV
    ]
    # Use filename as both key and value for direct matching
    for fname in report_filenames:
        report_map[fname.strip().lower()] = fname

    # prepare output dir
    output_dir.mkdir(parents=True, exist_ok=True)

    assigned_files = set()
    missing_ids = []
    summary = {}

    for cluster_id, id_list in clusters.items():
        cluster_folder = output_dir / cluster_id
        if not args.dry_run:
            cluster_folder.mkdir(parents=True, exist_ok=True)
        summary.setdefault(cluster_id, {'count': 0, 'files': []})

        for ident in id_list:
            ident_orig = str(ident)
            ident = ident_orig.strip().lower()
            chosen = []
            if args.verbose:
                print(
                    f"[SEARCH] Cluster: {cluster_id}, ID: {ident_orig} (normalized: {ident})")
                print(f"[SEARCH] Available files in {input_dir}:")
                for f in input_dir.iterdir():
                    print(f"    {f.name}")
            # if reports csv provided and maps to a filename, use it
            if report_map and ident in report_map:
                fname = report_map[ident]
                candidate = input_dir / fname
                if args.verbose:
                    print(
                        f"[REPORTS] id {ident_orig} mapped to filename '{fname}'")
                if candidate.exists():
                    chosen.append(candidate)
                else:
                    if args.verbose:
                        print(
                            f"[REPORTS] id {ident_orig} mapped to filename '{fname}' but file not found in {input_dir}")
            # otherwise search by heuristics
            if not chosen:
                found = find_matches_for_id(input_dir, ident, allowed_exts)
                if args.verbose:
                    print(
                        f"[HEURISTIC] Matches found: {[f.name for f in found]}")
                if found:
                    chosen.extend(found)
            if not chosen:
                missing_ids.append((cluster_id, ident_orig))
                if args.verbose:
                    print(
                        f"[MISSING] id {ident_orig} for cluster {cluster_id} -> no matching files found in {input_dir}")
                continue
            for src in chosen:
                dest = (cluster_folder / src.name)
                action = "copy" if not args.move else "move"
                if args.dry_run:
                    print(f"[DRY] {action} {src} -> {dest}")
                else:
                    if src.is_file():
                        if args.move:
                            shutil.move(str(src), str(dest))
                        else:
                            shutil.copy2(str(src), str(dest))
                        assigned_files.add(src.resolve())
                        summary[cluster_id]['count'] += 1
                        summary[cluster_id]['files'].append(str(dest))
                    else:
                        print(f"[SKIP] Source is not a file: {src}")

    # handle unassigned files (images left in input_dir that were not assigned)
    unassigned = []
    for pth in input_dir.iterdir():
        if not pth.is_file():
            continue
        if pth.suffix.lower().lstrip('.') not in allowed_exts:
            continue
        if pth.resolve() in assigned_files:
            continue
        unassigned.append(pth)

    if unassigned:
        unassigned_folder = output_dir / "_unassigned"
        if not args.dry_run:
            unassigned_folder.mkdir(parents=True, exist_ok=True)
        for src in unassigned:
            dest = unassigned_folder / src.name
            action = "copy" if not args.move else "move"
            if args.dry_run:
                print(f"[DRY] {action} {src} -> {dest}")
            else:
                if src.is_file():
                    if args.move:
                        shutil.move(str(src), str(dest))
                    else:
                        shutil.copy2(str(src), str(dest))
                else:
                    print(f"[SKIP] Unassigned source is not a file: {src}")

    # print summary
    print("\n=== ARRANGE SUMMARY ===")
    total_assigned = sum(v['count'] for v in summary.values())
    print(f"Clusters processed: {len(summary)}")
    print(f"Total assigned files: {total_assigned}")
    print(
        f"Unassigned files moved to: {str(output_dir / '_unassigned') if unassigned else 'None'}")
    print(f"Missing ids (no file found): {len(missing_ids)}")
    if missing_ids:
        print("Example missing ids (cluster_id, id):")
        for cluster_id, ident in missing_ids[:10]:
            print("  ", cluster_id, ident)
    print("Done.")


if __name__ == "__main__":
    main()
