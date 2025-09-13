#!/usr/bin/env python3
"""
arrange_by_headers.py

A script to automatically copy and rearrange screenshots into separate subfolders
based on their cropped headers (normalized OCR text).

Usage:
    python arrange_by_headers.py /path/to/input_images /path/to/ocr_results.csv /path/to/output_dir

Options:
    --move                          Move files instead of copying
    --similarity-threshold 0.8      Similarity threshold for grouping headers (0.0-1.0, default: 0.8)
    --min-group-size 2              Minimum number of screenshots to form a group (default: 2)
    --ext jpg,png,jpeg              Allowed extensions (comma-separated)
    --dry-run                       Don't actually copy/move; just print actions
    --verbose                       Print extra logging
    --use-fuzzy-matching            Use fuzzy string matching for grouping similar headers
"""

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    print("Warning: rapidfuzz not available. Fuzzy matching will be disabled.")


def load_ocr_results(ocr_csv_path: Path) -> Dict[str, Dict]:
    """Load OCR results from CSV file."""
    ocr_data = {}
    
    try:
        with open(ocr_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = row['filename']
                ocr_data[filename] = {
                    'ocr_text': row.get('ocr_text', '').strip(),
                    'ocr_confidence': float(row.get('ocr_confidence', 0)),
                    'normalized_text': row.get('normalized_text', '').strip()
                }
    except Exception as e:
        print(f"Error loading OCR results: {e}")
        sys.exit(1)
    
    return ocr_data


def clean_header_text(text: str) -> str:
    """Clean and normalize header text for grouping."""
    if not text:
        return "empty_header"
    
    # Remove common noise words and patterns
    text = text.lower().strip()
    
    # Remove very short texts (likely noise)
    if len(text) < 3:
        return "short_text"
    
    return text


def group_by_exact_match(ocr_data: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Group files by exact normalized text match."""
    groups = defaultdict(list)
    
    for filename, data in ocr_data.items():
        normalized_text = clean_header_text(data['normalized_text'])
        groups[normalized_text].append(filename)
    
    return dict(groups)


def group_by_fuzzy_match(ocr_data: Dict[str, Dict], threshold: float = 0.8) -> Dict[str, List[str]]:
    """Group files by fuzzy matching of normalized text."""
    if not RAPIDFUZZ_AVAILABLE:
        print("Warning: Fuzzy matching requested but rapidfuzz not available. Using exact matching.")
        return group_by_exact_match(ocr_data)
    
    groups = {}
    processed = set()
    
    for filename, data in ocr_data.items():
        if filename in processed:
            continue
        
        normalized_text = clean_header_text(data['normalized_text'])
        group_key = f"group_{len(groups) + 1}_{normalized_text[:20]}"
        groups[group_key] = [filename]
        processed.add(filename)
        
        # Find similar texts
        for other_filename, other_data in ocr_data.items():
            if other_filename in processed:
                continue
            
            other_normalized = clean_header_text(other_data['normalized_text'])
            
            # Calculate similarity
            similarity = fuzz.ratio(normalized_text, other_normalized) / 100.0
            
            if similarity >= threshold:
                groups[group_key].append(other_filename)
                processed.add(other_filename)
    
    return groups


def create_meaningful_group_names(groups: Dict[str, List[str]], ocr_data: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Create meaningful group names based on error messages, error types, and diagnostic patterns."""
    renamed_groups = {}
    
    for group_key, filenames in groups.items():
        if not filenames:
            continue
        
        # Get the normalized text for this group
        sample_filename = filenames[0]
        normalized_text = clean_header_text(ocr_data[sample_filename]['normalized_text'])
        
        # Create meaningful folder name based on error patterns and diagnostics
        if not normalized_text or normalized_text == "empty_header":
            folder_name = "empty_headers"
        elif normalized_text == "short_text":
            folder_name = "short_text"
        
        # Error Categories
        elif "rate card version not found" in normalized_text:
            folder_name = "rate_card_errors"
        elif "enable stockout" in normalized_text:
            folder_name = "stockout_settings"
        elif "err_mysql_connection" in normalized_text or "mysql_connection" in normalized_text:
            folder_name = "database_connection_errors"
        elif "axioserror" in normalized_text or "request failed with status code" in normalized_text:
            folder_name = "api_request_errors"
        elif "unable to connect" in normalized_text or "please check your internet connection" in normalized_text:
            folder_name = "network_connection_errors"
        elif "connection restored" in normalized_text:
            folder_name = "connection_restored"
        elif any(word in normalized_text for word in ["error", "failed", "exception"]):
            folder_name = "general_errors"
        
        # Functional Categories
        elif "welcome" in normalized_text:
            folder_name = "welcome_screens"
        elif "add sale" in normalized_text:
            folder_name = "add_sale_screens"
        elif "receive supply order" in normalized_text or "receive my inventory" in normalized_text:
            folder_name = "inventory_receiving"
        elif "morning" in normalized_text or "evening" in normalized_text:
            folder_name = "time_based_screens"
        elif "pbtno" in normalized_text or "pbtn" in normalized_text:
            folder_name = "transaction_screens"
        elif "sults" in normalized_text and "ailenev" in normalized_text:
            folder_name = "sults_ailenev_screens"
        elif any(word in normalized_text for word in ["inventory", "stock", "crate"]):
            folder_name = "inventory_management"
        elif "tracker status" in normalized_text or "running started" in normalized_text:
            folder_name = "tracker_status"
        elif "drafts" in normalized_text:
            folder_name = "draft_screens"
        elif "weekly roster entry" in normalized_text:
            folder_name = "roster_management"
        elif "bluetooth weighing machine" in normalized_text:
            folder_name = "hardware_settings"
        elif "cash summary" in normalized_text:
            folder_name = "financial_reports"
        elif "closing stock" in normalized_text or "stock varian" in normalized_text:
            folder_name = "stock_reports"
        elif "product weight amount" in normalized_text:
            folder_name = "product_management"
        elif "weighing machine" in normalized_text:
            folder_name = "weighing_system"
        
        # UI/UX Categories
        elif "google play" in normalized_text:
            folder_name = "app_store_screens"
        elif "phone" in normalized_text and "incoming call" in normalized_text:
            folder_name = "phone_call_screens"
        elif "calculator" in normalized_text:
            folder_name = "calculator_screens"
        elif "truecaller" in normalized_text:
            folder_name = "truecaller_screens"
        
        # Content Categories
        elif any(word in normalized_text for word in ["potato", "tomato", "onion", "carrot", "vegetable", "fruit"]):
            folder_name = "product_catalog"
        elif any(word in normalized_text for word in ["arai keerai", "tamato", "cash bag"]):
            folder_name = "product_items"
        
        else:
            # Use first 30 characters of normalized text, replace spaces with underscores
            folder_name = normalized_text[:30].replace(" ", "_").replace("/", "_").replace("\\", "_")
            # Remove any remaining problematic characters
            folder_name = "".join(c for c in folder_name if c.isalnum() or c in "_-")
            if not folder_name:
                folder_name = "other_screens"
        
        # Add count suffix if duplicate
        base_name = folder_name
        counter = 1
        while folder_name in renamed_groups:
            folder_name = f"{base_name}_{counter}"
            counter += 1
        
        renamed_groups[folder_name] = filenames
    
    return renamed_groups


def find_image_file(input_dir: Path, filename: str, allowed_exts: Set[str]) -> Path:
    """Find the actual image file in the input directory."""
    # Try exact match first
    exact_match = input_dir / filename
    if exact_match.exists() and exact_match.suffix.lower().lstrip('.') in allowed_exts:
        return exact_match
    
    # Try without bug_reports prefix
    if filename.startswith('bug_reports_'):
        alt_name = filename[12:]  # Remove 'bug_reports_' prefix
        alt_path = input_dir / alt_name
        if alt_path.exists() and alt_path.suffix.lower().lstrip('.') in allowed_exts:
            return alt_path
    
    # Try with bug_reports prefix
    if not filename.startswith('bug_reports_'):
        alt_name = f"bug_reports_{filename}"
        alt_path = input_dir / alt_name
        if alt_path.exists() and alt_path.suffix.lower().lstrip('.') in allowed_exts:
            return alt_path
    
    # Try stem matching
    stem = Path(filename).stem
    for file in input_dir.iterdir():
        if (file.is_file() and 
            file.suffix.lower().lstrip('.') in allowed_exts and
            (file.stem == stem or stem in file.stem or file.stem in stem)):
            return file
    
    return None


def arrange_by_headers(input_dir: Path, ocr_csv: Path, output_dir: Path, 
                      use_fuzzy: bool = False, similarity_threshold: float = 0.8,
                      min_group_size: int = 2, allowed_exts: Set[str] = None,
                      move_files: bool = False, dry_run: bool = False, 
                      verbose: bool = False) -> None:
    """Main function to arrange screenshots by headers."""
    
    if allowed_exts is None:
        allowed_exts = {'jpg', 'jpeg', 'png'}
    
    print("Loading OCR results...")
    ocr_data = load_ocr_results(ocr_csv)
    
    if verbose:
        print(f"Loaded OCR data for {len(ocr_data)} files")
    
    print("Grouping files by header content...")
    if use_fuzzy:
        groups = group_by_fuzzy_match(ocr_data, similarity_threshold)
    else:
        groups = group_by_exact_match(ocr_data)
    
    print("Creating meaningful group names...")
    groups = create_meaningful_group_names(groups, ocr_data)
    
    # Filter groups by minimum size
    filtered_groups = {k: v for k, v in groups.items() if len(v) >= min_group_size}
    
    # Handle single files (smaller than min_group_size)
    single_files = []
    for k, v in groups.items():
        if len(v) < min_group_size:
            single_files.extend(v)
    
    if single_files:
        filtered_groups['single_files'] = single_files
    
    groups = filtered_groups
    
    if verbose:
        print(f"Created {len(groups)} groups:")
        for group_name, files in groups.items():
            print(f"  {group_name}: {len(files)} files")
    
    # Create output directory
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy/move files to their respective groups
    print(f"\n{'Moving' if move_files else 'Copying'} files to group folders...")
    
    total_processed = 0
    missing_files = []
    
    for group_name, filenames in groups.items():
        group_folder = output_dir / group_name
        
        if not dry_run:
            group_folder.mkdir(parents=True, exist_ok=True)
        
        if verbose:
            print(f"\nProcessing group '{group_name}' ({len(filenames)} files):")
        
        for filename in filenames:
            source_file = find_image_file(input_dir, filename, allowed_exts)
            
            if source_file is None:
                missing_files.append((group_name, filename))
                if verbose:
                    print(f"  Missing: {filename}")
                continue
            
            dest_file = group_folder / source_file.name
            action = "move" if move_files else "copy"
            
            if dry_run:
                print(f"  [DRY] {action} {source_file} -> {dest_file}")
            else:
                try:
                    if move_files:
                        shutil.move(str(source_file), str(dest_file))
                    else:
                        shutil.copy2(str(source_file), str(dest_file))
                    
                    total_processed += 1
                    if verbose:
                        print(f"  {action.title()}d: {source_file.name}")
                        
                except Exception as e:
                    print(f"  Error processing {filename}: {e}")
    
    # Summary
    print(f"\n=== ARRANGE BY HEADERS SUMMARY ===")
    print(f"Groups created: {len(groups)}")
    print(f"Total files processed: {total_processed}")
    print(f"Missing files: {len(missing_files)}")
    
    if missing_files and len(missing_files) <= 10:
        print("Missing files:")
        for group_name, filename in missing_files:
            print(f"  {group_name}: {filename}")
    elif missing_files:
        print(f"Missing files (showing first 10 of {len(missing_files)}):")
        for group_name, filename in missing_files[:10]:
            print(f"  {group_name}: {filename}")
    
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Arrange screenshots into folders based on cropped headers (OCR text)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('input_dir', type=Path, help='Input images directory')
    parser.add_argument('ocr_csv', type=Path, help='OCR results CSV file')
    parser.add_argument('output_dir', type=Path, help='Output directory')
    
    parser.add_argument('--move', action='store_true',
                       help='Move files instead of copying')
    parser.add_argument('--use-fuzzy-matching', action='store_true',
                       help='Use fuzzy string matching for grouping similar headers')
    parser.add_argument('--similarity-threshold', type=float, default=0.8,
                       help='Similarity threshold for fuzzy matching (0.0-1.0, default: 0.8)')
    parser.add_argument('--min-group-size', type=int, default=2,
                       help='Minimum number of screenshots to form a group (default: 2)')
    parser.add_argument('--ext', type=str, default='jpg,png,jpeg',
                       help='Allowed extensions (comma-separated)')
    parser.add_argument('--dry-run', action='store_true',
                       help="Don't actually copy/move; just print actions")
    parser.add_argument('--verbose', action='store_true', 
                       help='Verbose logging')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.input_dir.exists() or not args.input_dir.is_dir():
        print(f"ERROR: Input directory not found or not a directory: {args.input_dir}")
        sys.exit(2)
    
    if not args.ocr_csv.exists():
        print(f"ERROR: OCR CSV file not found: {args.ocr_csv}")
        sys.exit(2)
    
    # Parse allowed extensions
    allowed_exts = {ext.strip().lower() for ext in args.ext.split(',') if ext.strip()}
    
    # Validate similarity threshold
    if not 0.0 <= args.similarity_threshold <= 1.0:
        print("ERROR: Similarity threshold must be between 0.0 and 1.0")
        sys.exit(2)
    
    # Validate min group size
    if args.min_group_size < 1:
        print("ERROR: Minimum group size must be at least 1")
        sys.exit(2)
    
    # Run the arrangement
    arrange_by_headers(
        input_dir=args.input_dir,
        ocr_csv=args.ocr_csv,
        output_dir=args.output_dir,
        use_fuzzy=args.use_fuzzy_matching,
        similarity_threshold=args.similarity_threshold,
        min_group_size=args.min_group_size,
        allowed_exts=allowed_exts,
        move_files=args.move,
        dry_run=args.dry_run,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
