# Arrange Screenshots by Headers

This document explains how to use the `arrange_by_headers.py` script to automatically organize screenshots into separate subfolders based on their header content.

## Overview

The script takes screenshots and their corresponding OCR results, then groups similar screenshots together based on the normalized text extracted from their headers. This is useful for organizing large collections of mobile app screenshots by their screen types or content.

## Quick Run Command

```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers --min-group-size 2 --verbose
```

## Usage

### Basic Command

```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers
```

### Options

- `--move` - Move files instead of copying them
- `--min-group-size N` - Minimum number of screenshots to form a group (default: 2)
- `--use-fuzzy-matching` - Use fuzzy string matching for grouping similar headers (requires rapidfuzz)
- `--similarity-threshold 0.8` - Similarity threshold for fuzzy matching (0.0-1.0, default: 0.8)
- `--ext jpg,png,jpeg` - Allowed file extensions (comma-separated)
- `--dry-run` - Don't actually copy/move files; just show what would happen
- `--verbose` - Print detailed logging information

### Examples

#### Basic usage (copy mode):
```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers
```

#### Move files instead of copying:
```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers --move
```

#### Create more detailed groups (minimum 2 files per group):
```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers --min-group-size 2 --verbose
```

#### Test without making changes (dry run):
```bash
python scripts/arrange_by_headers.py input_screenshots outputs/ocr_results.csv outputs/arranged_by_headers --dry-run --verbose
```

## Output Structure

The script creates folders based on the header content patterns:

- **welcome_screens** - Screenshots with "welcome" text in headers
- **add_sale_screens** - Screenshots with "add sale" functionality
- **rate_card_error_screens** - Screenshots showing "rate card version not found" errors
- **empty_headers** - Screenshots with empty or minimal header content
- **transaction_screens** - Screenshots with transaction-related content (PBTNO codes)
- **inventory_screens** - Screenshots related to inventory management
- **error_screens** - Screenshots showing various error messages
- **single_files** - Screenshots that don't have enough similar matches

## How It Works

1. **Load OCR Data**: Reads the OCR results CSV file containing filename, OCR text, and normalized text
2. **Group by Content**: Groups screenshots based on exact matches of normalized header text
3. **Create Meaningful Names**: Assigns descriptive folder names based on content patterns
4. **Filter by Size**: Only creates groups with at least `min-group-size` files
5. **Arrange Files**: Copies or moves screenshots to their respective group folders

## Requirements

- Python 3.8+
- OCR results CSV file with columns: `filename`, `ocr_text`, `ocr_confidence`, `normalized_text`
- Input directory containing the screenshot files
- Optional: `rapidfuzz` library for fuzzy matching (install with `pip install rapidfuzz`)

## Output Summary

After running, the script provides a summary showing:
- Number of groups created
- Total files processed
- Number of missing files (if any)
- Examples of missing files (if applicable)

This helps you understand how well the grouping worked and if any files couldn't be matched.
