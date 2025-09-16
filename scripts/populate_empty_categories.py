#!/usr/bin/env python3
"""
populate_empty_categories.py

A script to create an exact duplicate of the Firebase export JSON and populate
empty category fields in the duplicate using existing categorization logic.

The original file remains completely unchanged.

Usage:
    python populate_empty_categories.py <original_json_file> [options]

Options:
    --ocr-csv <path>        Path to OCR results CSV (default: ocr_results.csv)
    --output-suffix <str>   Suffix for output file (default: _processed)
    --verbose               Print detailed logging
    --dry-run              Show what would be done without making changes
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote, urlparse

# Import the existing categorization logic
sys.path.append(str(Path(__file__).parent))
from arrange_by_headers import (
    load_ocr_results, 
    categorize_screenshot_content,
    clean_header_text
)


def create_exact_duplicate(original_file: Path, output_file: Path, verbose: bool = False) -> None:
    """Create an exact byte-for-byte duplicate of the original JSON file."""
    if verbose:
        print(f"Creating exact duplicate: {original_file} -> {output_file}")
    
    # Use shutil.copy2 to preserve metadata and create exact duplicate
    shutil.copy2(str(original_file), str(output_file))
    
    if verbose:
        print(f"Duplicate created successfully")


def extract_filename_from_url(url: str) -> str:
    """Extract the filename from a Firebase Storage URL (URL-decoded, without query)."""
    try:
        parsed = urlparse(url)
        path = parsed.path  # e.g., /v0/b/.../o/bug_reports%2Fscaled_123.jpg
        # filename is the last segment after '/'
        last_segment = path.rsplit('/', 1)[-1]
        # URLs often encode folder prefix like bug_reports%2F<filename>
        decoded = unquote(last_segment)
        if '%2F' in last_segment:
            decoded = unquote(last_segment)
        # If there is still a folder prefix like 'bug_reports/<file>' keep only basename
        if '/' in decoded:
            decoded = decoded.rsplit('/', 1)[-1]
        # Strip any query params if present (already separated by urlparse), but be safe
        if '?' in decoded:
            decoded = decoded.split('?', 1)[0]
        return decoded
    except Exception:
        return ""


def get_category_from_filename(filename: str, ocr_data: Dict) -> str:
    """Get category for a filename using existing categorization logic."""
    if not filename or filename not in ocr_data:
        return None
    
    # Get the normalized text for this filename
    normalized_text = clean_header_text(ocr_data[filename]['normalized_text'])
    
    # Use the existing categorization logic
    category = categorize_screenshot_content(normalized_text, ocr_data, [filename])
    
    return category


def get_fallback_category(entry: Dict, attachments: List[str], verbose: bool = False) -> str:
    """
    Provide fallback categorization when OCR-based categorization fails.
    Uses metadata and heuristics to assign reasonable categories.
    """
    # Check if there are attachments
    if not attachments:
        return "no_attachments"
    
    # Analyze attachment URLs for patterns
    for url in attachments:
        filename = extract_filename_from_url(url)
        if not filename:
            continue
            
        filename_lower = filename.lower()
        
        # Pattern-based categorization from filename
        if 'screenshot' in filename_lower:
            # Try to infer from screenshot naming patterns
            if 'error' in filename_lower or 'exception' in filename_lower:
                return "error_screenshots"
            elif 'login' in filename_lower or 'signin' in filename_lower:
                return "login_screenshots"
            elif 'menu' in filename_lower or 'home' in filename_lower:
                return "navigation_screenshots"
            else:
                return "general_screenshots"
        
        # File type patterns
        if filename_lower.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            return "image_attachments"
        elif filename_lower.endswith('.txt'):
            return "log_files"
    
    # Check other metadata for clues
    comment = entry.get('comment', '').lower()
    if comment:
        if any(error_word in comment for error_word in ['error', 'bug', 'issue', 'problem']):
            return "reported_issues"
        elif any(feature_word in comment for feature_word in ['feature', 'request', 'enhancement']):
            return "feature_requests"
    
    # Check creation date patterns (if useful for categorization)
    created_at = entry.get('createdAt', '')
    if created_at:
        # Could add time-based categorization if needed
        pass
    
    # Check if user info suggests test data
    name = entry.get('name', '')
    email = entry.get('email', '')
    if 'test' in name.lower() or 'test' in email.lower():
        return "test_data"
    
    # Default fallback for records that can't be categorized
    return "missing_ocr_data"


def populate_empty_categories_in_duplicate(duplicate_file: Path, ocr_data: Dict, 
                                         dry_run: bool = False, verbose: bool = False) -> int:
    """
    Populate ALL missing or empty category fields in the duplicate JSON file.
    Ensures every record has a non-empty category field.
    Returns the number of records updated.
    """
    if verbose:
        print(f"Processing duplicate file: {duplicate_file}")
    
    # Load the duplicate JSON
    with open(duplicate_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updates = 0
    processed_records = 0
    
    for key, entry in data.items():
        processed_records += 1
        try:
            # Check if category field is missing or empty
            current_category = entry.get('category', '')
            if current_category and current_category.strip():
                # Skip if category already has a non-empty value
                continue
            
            # Get attachments to find filenames
            attachments = entry.get('attachments', []) or []
            found_category = None
            
            # Try to categorize based on attachments
            for url in attachments:
                filename = extract_filename_from_url(url)
                if not filename:
                    continue
                
                # Try direct match first
                category = get_category_from_filename(filename, ocr_data)
                if category:
                    found_category = category
                    break
                
                # Try with and without 'bug_reports_' prefix
                if filename.startswith('bug_reports_'):
                    alt_filename = filename[len('bug_reports_'):]
                    category = get_category_from_filename(alt_filename, ocr_data)
                    if category:
                        found_category = category
                        break
                else:
                    alt_filename = f"bug_reports_{filename}"
                    category = get_category_from_filename(alt_filename, ocr_data)
                    if category:
                        found_category = category
                        break
            
            # Fallback categorization if no OCR-based category found
            if not found_category:
                found_category = get_fallback_category(entry, attachments, verbose)
            
            # Ensure we always have a category
            if not found_category:
                found_category = "uncategorized"
            
            # Update the category
            if verbose:
                status = "missing" if 'category' not in entry else "empty"
                print(f"  Record {key}: updating {status} category to '{found_category}'")
            
            if not dry_run:
                entry['category'] = found_category
            updates += 1
                
        except Exception as e:
            if verbose:
                print(f"  Error processing record {key}: {e}")
            # Ensure even error cases get a category
            if not dry_run:
                entry['category'] = "uncategorized"
            updates += 1
            continue
    
    # Save the updated duplicate file
    if updates > 0 and not dry_run:
        with open(duplicate_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    if verbose:
        print(f"Processed {processed_records} records, updated {updates} categories")
    
    return updates


def main():
    parser = argparse.ArgumentParser(
        description="Populate empty category fields in Firebase export JSON duplicate",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('json_file', type=Path, 
                       help='Original Firebase export JSON file')
    parser.add_argument('--ocr-csv', type=Path, default='ocr_results.csv',
                       help='Path to OCR results CSV (default: ocr_results.csv)')
    parser.add_argument('--output-suffix', type=str, default='_processed',
                       help='Suffix for output file (default: _processed)')
    parser.add_argument('--dry-run', action='store_true',
                       help="Show what would be done without making changes")
    parser.add_argument('--verbose', action='store_true', 
                       help='Verbose logging')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.json_file.exists():
        print(f"ERROR: JSON file not found: {args.json_file}")
        sys.exit(1)
    
    if not args.ocr_csv.exists():
        print(f"ERROR: OCR CSV file not found: {args.ocr_csv}")
        sys.exit(1)
    
    # Create output filename
    stem = args.json_file.stem
    suffix = args.json_file.suffix
    output_file = args.json_file.parent / f"{stem}{args.output_suffix}{suffix}"
    
    print("=== POPULATE EMPTY CATEGORIES PIPELINE ===")
    print(f"Original file: {args.json_file}")
    print(f"Output file: {output_file}")
    print(f"OCR data: {args.ocr_csv}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    # Step 1: Load OCR data
    print("Step 1: Loading OCR results...")
    ocr_data = load_ocr_results(args.ocr_csv)
    if args.verbose:
        print(f"Loaded OCR data for {len(ocr_data)} files")
    
    # Step 2: Create exact duplicate
    print("Step 2: Creating exact duplicate of original JSON...")
    if not args.dry_run:
        create_exact_duplicate(args.json_file, output_file, args.verbose)
    else:
        print(f"[DRY RUN] Would create: {output_file}")
    
    # Step 3: Populate empty categories in duplicate only
    print("Step 3: Populating empty category fields in duplicate...")
    if not args.dry_run:
        updates = populate_empty_categories_in_duplicate(
            output_file, ocr_data, args.dry_run, args.verbose
        )
    else:
        # For dry run, work with original file but don't save
        updates = populate_empty_categories_in_duplicate(
            args.json_file, ocr_data, args.dry_run, args.verbose
        )
    
    # Summary
    print("\n=== PIPELINE SUMMARY ===")
    print(f"Original file: {args.json_file} (UNCHANGED)")
    print(f"Processed file: {output_file}")
    print(f"Empty categories populated: {updates}")
    
    if args.dry_run:
        print("NOTE: This was a dry run. No files were modified.")
    else:
        print("Pipeline completed successfully!")


if __name__ == "__main__":
    main()
