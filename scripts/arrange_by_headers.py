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
from urllib.parse import unquote, urlparse

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
    """Group files by exact normalized text match and content patterns."""
    groups = defaultdict(list)
    
    for filename, data in ocr_data.items():
        normalized_text = clean_header_text(data['normalized_text'])
        
        # Use content-based grouping instead of exact text matching
        group_key = get_content_group_key(normalized_text)
        groups[group_key].append(filename)
    
    return dict(groups)


def get_content_group_key(normalized_text: str) -> str:
    """Get a group key based on content patterns rather than exact text."""
    if not normalized_text or normalized_text == "empty_header":
        return "empty_headers"
    
    text_lower = normalized_text.lower()
    
    # Pattern-based grouping for common content types
    import re
    
    # PBTNO patterns (transaction codes) - group by pattern, not exact code
    if re.search(r'pbtno\d+', text_lower):
        return "pbtno_transaction_pattern"
    
    # Time patterns - group by time format, not exact time
    if re.search(r'\d{1,2}:\d{2}', text_lower):
        return "time_based_content"
    
    # Welcome patterns
    if 'welcome' in text_lower:
        return "welcome_content"
    
    # Add sale patterns
    if 'add sale' in text_lower:
        return "add_sale_content"
    
    # Error patterns
    if any(error_word in text_lower for error_word in ['error', 'failed', 'exception', 'timeout']):
        return "error_content"
    
    # Connection patterns
    if 'connection' in text_lower:
        return "connection_content"
    
    # Rate card patterns
    if 'rate card' in text_lower:
        return "rate_card_content"
    
    # Stockout patterns
    if 'stockout' in text_lower:
        return "stockout_content"
    
    # Inventory patterns
    if any(inv_word in text_lower for inv_word in ['inventory', 'stock', 'crate']):
        return "inventory_content"
    
    # Product patterns
    if any(prod_word in text_lower for prod_word in ['product', 'item', 'catalog']):
        return "product_content"
    
    # Settings patterns
    if any(settings_word in text_lower for settings_word in ['settings', 'preferences', 'configuration']):
        return "settings_content"
    
    # Menu/Navigation patterns
    if any(nav_word in text_lower for nav_word in ['menu', 'navigation', 'home', 'dashboard']):
        return "navigation_content"
    
    # Form patterns
    if any(form_word in text_lower for form_word in ['form', 'input', 'field', 'enter']):
        return "form_content"
    
    # Calculator patterns
    if 'calculator' in text_lower:
        return "calculator_content"
    
    # Phone patterns
    if any(phone_word in text_lower for phone_word in ['phone', 'call', 'contact']):
        return "phone_content"
    
    # App store patterns
    if any(store_word in text_lower for store_word in ['app store', 'play store', 'google play']):
        return "app_store_content"
    
    # Financial patterns
    if any(fin_word in text_lower for fin_word in ['financial', 'report', 'analytics', 'cash', 'summary']):
        return "financial_content"
    
    # Weighing patterns
    if any(weight_word in text_lower for weight_word in ['weighing', 'weight', 'scale']):
        return "weighing_content"
    
    # Tracker patterns
    if any(tracker_word in text_lower for tracker_word in ['tracker', 'status', 'running']):
        return "tracker_content"
    
    # Roster patterns
    if any(roster_word in text_lower for roster_word in ['roster', 'employee', 'staff']):
        return "roster_content"
    
    # Bug report patterns
    if any(bug_word in text_lower for bug_word in ['bug', 'describe', 'issue', 'report']):
        return "bug_report_content"
    
    # If we can't categorize, try to extract meaningful words for grouping
    meaningful_words = extract_meaningful_words(normalized_text)
    if meaningful_words:
        return f"misc_{meaningful_words[:20]}"
    
    # Default to unclassified
    return "unclassified_content"


def group_by_fuzzy_match(ocr_data: Dict[str, Dict], threshold: float = 0.8) -> Dict[str, List[str]]:
    """Group files by fuzzy matching of normalized text with content-based grouping."""
    if not RAPIDFUZZ_AVAILABLE:
        print("Warning: Fuzzy matching requested but rapidfuzz not available. Using content-based matching.")
        return group_by_exact_match(ocr_data)
    
    # First, use content-based grouping to create initial groups
    content_groups = group_by_exact_match(ocr_data)
    
    # Then, within each content group, use fuzzy matching to merge similar groups
    final_groups = {}
    processed_groups = set()
    
    for group_key, filenames in content_groups.items():
        if group_key in processed_groups:
            continue
        
        # Start with this group
        merged_group = filenames.copy()
        processed_groups.add(group_key)
        
        # Find other groups with similar content
        for other_group_key, other_filenames in content_groups.items():
            if other_group_key in processed_groups or other_group_key == group_key:
                continue
            
            # Check if groups are similar using fuzzy matching on sample texts
            if are_groups_similar(group_key, other_group_key, ocr_data, threshold):
                merged_group.extend(other_filenames)
                processed_groups.add(other_group_key)
        
        # Use the original group key or create a better one
        final_groups[group_key] = merged_group
    
    return final_groups


def are_groups_similar(group1_key: str, group2_key: str, ocr_data: Dict, threshold: float) -> bool:
    """Check if two groups are similar enough to merge."""
    # Get sample texts from each group
    group1_samples = []
    group2_samples = []
    
    # Find sample files from each group (limit to avoid performance issues)
    for filename, data in ocr_data.items():
        normalized_text = clean_header_text(data['normalized_text'])
        group_key = get_content_group_key(normalized_text)
        
        if group_key == group1_key and len(group1_samples) < 3:
            group1_samples.append(normalized_text)
        elif group_key == group2_key and len(group2_samples) < 3:
            group2_samples.append(normalized_text)
    
    # Compare samples using fuzzy matching
    for sample1 in group1_samples:
        for sample2 in group2_samples:
            similarity = fuzz.ratio(sample1, sample2) / 100.0
            if similarity >= threshold:
                return True
    
    return False


def create_meaningful_group_names(groups: Dict[str, List[str]], ocr_data: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Create meaningful group names based on content analysis and patterns."""
    renamed_groups = {}
    
    for group_key, filenames in groups.items():
        if not filenames:
            continue
        
        # Get the normalized text for this group
        sample_filename = filenames[0]
        normalized_text = clean_header_text(ocr_data[sample_filename]['normalized_text'])
        
        # Analyze the content to determine the most appropriate category
        folder_name = categorize_screenshot_content(normalized_text, ocr_data, filenames)
        
        # Handle duplicate folder names
        original_folder_name = folder_name
        counter = 1
        while folder_name in renamed_groups:
            folder_name = f"{original_folder_name}_{counter}"
            counter += 1
        
        renamed_groups[folder_name] = filenames
    
    return renamed_groups


def categorize_screenshot_content(normalized_text: str, ocr_data: Dict, filenames: List[str]) -> str:
    """Categorize screenshot content into meaningful groups."""
    
    # If no meaningful text, check if it's truly empty or just garbled
    if not normalized_text or normalized_text == "empty_header":
        return "unclear_insufficient_info"
    
    if normalized_text == "short_text":
        return "unclear_insufficient_info"
    
    # Convert to lowercase for pattern matching
    text_lower = normalized_text.lower()
    
    # ERROR CATEGORIES - Most important to identify first
    if "rate card version not found" in text_lower:
        return "functional_errors"
    elif "mysql" in text_lower and ("connection" in text_lower or "failed" in text_lower):
        return "connectivity_problems"
    elif "axioserror" in text_lower or ("status code" in text_lower and "error" in text_lower):
        return "connectivity_problems"
    elif "unable to connect" in text_lower or ("connection" in text_lower and "error" in text_lower):
        return "connectivity_problems"
    elif "connection restored" in text_lower or "reconnected" in text_lower:
        return "connectivity_problems"
    elif any(error_word in text_lower for error_word in ["error", "failed", "exception", "timeout"]):
        return "functional_errors"
    
    # FUNCTIONAL CATEGORIES - Core app functionality
    elif "add sale" in text_lower or "new sale" in text_lower:
        return "functional_errors"
    elif "enable stockout" in text_lower or "stockout" in text_lower:
        return "configuration_settings"
    elif "welcome" in text_lower or "login" in text_lower or "sign in" in text_lower:
        return "authentication_access"
    elif "transaction" in text_lower or "payment" in text_lower or "checkout" in text_lower:
        return "integration_failures"
    elif "inventory" in text_lower and ("manage" in text_lower or "list" in text_lower):
        return "functional_errors"
    elif "inventory" in text_lower and "receiv" in text_lower:
        return "functional_errors"
    elif "product" in text_lower and ("catalog" in text_lower or "list" in text_lower):
        return "functional_errors"
    elif "product" in text_lower and ("item" in text_lower or "detail" in text_lower):
        return "functional_errors"
    elif "roster" in text_lower or "employee" in text_lower:
        return "functional_errors"
    elif "time" in text_lower or "clock" in text_lower or "schedule" in text_lower:
        return "functional_errors"
    elif "phone" in text_lower or "call" in text_lower or "contact" in text_lower:
        return "integration_failures"
    elif "app store" in text_lower or "play store" in text_lower:
        return "compatibility_issues"
    elif "financial" in text_lower or "report" in text_lower or "analytics" in text_lower:
        return "data_integrity_issues"
    elif "weighing" in text_lower or "weight" in text_lower or "scale" in text_lower:
        return "integration_failures"
    elif "tracker" in text_lower or "status" in text_lower:
        return "functional_errors"
    elif "bug" in text_lower or "describe" in text_lower or "issue" in text_lower:
        return "unclear_insufficient_info"
    
    # UI/NAVIGATION CATEGORIES
    elif any(nav_word in text_lower for nav_word in ["menu", "navigation", "home", "dashboard"]):
        return "ui_ux_issues"
    elif any(settings_word in text_lower for settings_word in ["settings", "preferences", "configuration"]):
        return "configuration_settings"
    elif any(search_word in text_lower for search_word in ["search", "filter", "find"]):
        return "ui_ux_issues"
    elif any(list_word in text_lower for list_word in ["list", "table", "grid", "view"]):
        return "ui_ux_issues"
    elif any(form_word in text_lower for form_word in ["form", "input", "field", "enter"]):
        return "ui_ux_issues"
    
    # If we can't categorize, try to extract meaningful words
    meaningful_words = extract_meaningful_words(normalized_text)
    if meaningful_words:
        return "unclear_insufficient_info"
    else:
        return "unclear_insufficient_info"


def extract_meaningful_words(text: str) -> str:
    """Extract meaningful words from garbled OCR text."""
    import re
    
    # Remove numbers, special characters, and very short words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out common OCR noise words
    noise_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'man', 'men', 'put', 'say', 'she', 'too', 'use'}
    
    meaningful_words = [word for word in words if word not in noise_words and len(word) > 2]
    
    # Return the most common meaningful words
    if meaningful_words:
        # Count word frequency
        from collections import Counter
        word_counts = Counter(meaningful_words)
        most_common = word_counts.most_common(3)
        return "_".join([word for word, count in most_common])
    
    return ""


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
                      verbose: bool = False, firebase_json: Path = None) -> None:
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
    filename_to_category: Dict[str, str] = {}
    
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
                    # Record mapping from filename to derived category
                    filename_to_category[source_file.name] = group_name
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
    
    # Optionally update Firebase export JSON with categories
    if firebase_json and not dry_run:
        try:
            _update_firebase_export_categories(firebase_json, filename_to_category, verbose)
        except Exception as e:
            print(f"Warning: Failed to update Firebase export JSON: {e}")
    print("Done.")


def _extract_filename_from_url(url: str) -> str:
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


def _update_firebase_export_categories(firebase_json_path: Path, filename_to_category: Dict[str, str], verbose: bool = False) -> None:
    """Open the Firebase RTDB export JSON and write category fields based on attachment filenames."""
    if verbose:
        print(f"Updating categories in JSON: {firebase_json_path}")
    with open(firebase_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updates = 0
    for key, entry in data.items():
        try:
            attachments = entry.get('attachments', []) or []
            found_category = None
            for url in attachments:
                fname = _extract_filename_from_url(url)
                if not fname:
                    continue
                # Direct match
                if fname in filename_to_category:
                    found_category = filename_to_category[fname]
                    break
                # Try with and without a common 'bug_reports_' prefix
                if fname.startswith('bug_reports_'):
                    alt = fname[len('bug_reports_'):]
                    if alt in filename_to_category:
                        found_category = filename_to_category[alt]
                        break
                else:
                    alt = f"bug_reports_{fname}"
                    if alt in filename_to_category:
                        found_category = filename_to_category[alt]
                        break
            if found_category:
                if entry.get('category', '') != found_category:
                    entry['category'] = found_category
                    updates += 1
        except Exception:
            continue

    if updates:
        with open(firebase_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if verbose:
            print(f"Updated category for {updates} records.")
    else:
        if verbose:
            print("No category updates were applied (no matching attachments found).")


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
    parser.add_argument('--firebase-json', type=Path, default=None,
                       help='Path to Firebase RTDB export JSON to update categories in-place')
    
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
        verbose=args.verbose,
        firebase_json=args.firebase_json
    )


if __name__ == "__main__":
    main()
