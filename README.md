# Autonomous Image Categorization Pipeline

A fully autonomous pipeline that processes Firebase export JSON files and categorizes images using OCR and intelligent heuristics.

## Features

- **Autonomous Operation**: Single command execution with no manual intervention required
- **Image Download**: Automatically downloads images from Firebase Storage URLs
- **OCR Processing**: Extracts text from images using Tesseract OCR
- **Intelligent Categorization**: Multi-strategy categorization using:
  - OCR text analysis
  - Filename pattern recognition
  - Metadata analysis
  - Robust fallback logic
- **Comprehensive Logging**: Detailed execution logs with statistics
- **Error Handling**: Defensive programming with graceful error recovery

## Quick Start

### Prerequisites

Install required dependencies:
```bash
pip install requests pillow pytesseract
```

**Note**: You'll also need to install Tesseract OCR on your system:
- Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
- macOS: `brew install tesseract`
- Linux: `sudo apt-get install tesseract-ocr`

### Basic Usage

Run the pipeline with default settings:
```bash
python run_pipeline.py
```

This will:
1. Process `signintest-84632-default-rtdb-active-export.json`
2. Download images to `input_screenshots/`
3. Generate `final_output.json` with all records categorized
4. Create `pipeline.log` with execution details

### Advanced Usage

```bash
# Custom input/output files
python run_pipeline.py --input my_data.json --output my_results.json

# Custom screenshots directory
python run_pipeline.py --screenshots-dir ./downloaded_images

# Dry run (preview without changes)
python run_pipeline.py --dry-run

# Verbose logging
python run_pipeline.py --verbose

# Combined options
python run_pipeline.py --input data.json --output results.json --verbose --dry-run
```

## Pipeline Process

1. **Input Validation**: Validates input JSON file exists and is readable
2. **Image Download**: Downloads all images from Firebase Storage URLs to local directory
3. **OCR Processing**: Extracts text from downloaded images using Tesseract
4. **Categorization**: Applies multiple categorization strategies:
   - OCR text pattern matching
   - Filename analysis
   - Record metadata analysis
   - Fallback categorization for edge cases
5. **Output Generation**: Creates final JSON with all records containing category fields
6. **Statistics**: Reports processing statistics and success rates

## Category Taxonomy

The pipeline uses a problem-focused taxonomy defined in `config/categories.json`.

Canonical category IDs:
- `functional_errors`
- `ui_ux_issues`
- `performance_issues`
- `connectivity_problems`
- `authentication_access`
- `data_integrity_issues`
- `crash_stability`
- `integration_failures`
- `configuration_settings`
- `compatibility_issues`
- `feature_requests`
- `unclear_insufficient_info`

Deterministic heuristics in `pipeline/mapping_rules.py` map OCR text, filenames, and comments to these categories. The same rules are applied in both `run_pipeline.py` and `scripts/populate_empty_categories.py` for consistency.

## Output Format

The output JSON maintains the same structure as the input but ensures every record has a `category` field:

```json
{
  "-OY04XVHntk9JZKXRYDE": {
    "attachments": ["https://firebasestorage.googleapis.com/..."],
    "category": "authentication_access",
    "comment": "",
    "createdAt": "2025-08-19 12:18:54.946506",
    "email": "",
    "hasResolved": false,
    "logFile": "https://firebasestorage.googleapis.com/...",
    "name": "+918667736001",
    "userId": "9213"
  }
}
```

## Logging

The pipeline creates detailed logs in `pipeline.log` including:
- Processing progress for each record
- Download success/failure details
- Categorization decisions and reasoning
- Error messages with context
- Final statistics summary

## Error Handling

The pipeline is designed to be robust:
- Network failures are logged but don't stop processing
- Invalid images are skipped with warnings
- OCR failures fall back to filename/metadata analysis
- Processing errors result in `unclear_insufficient_info` category (with detailed logs in pipeline.log)
- All records are guaranteed to have a category field

## Troubleshooting

### Common Issues

1. **Tesseract not found**: Install Tesseract OCR and ensure it's in your PATH
2. **Network timeouts**: Check internet connection, pipeline will retry failed downloads
3. **Permission errors**: Ensure write permissions for output directory
4. **Memory issues**: For large datasets, monitor system memory usage

### Debug Mode

Run with `--verbose` flag for detailed debugging information:
```bash
python run_pipeline.py --verbose
```

## Performance

- Processing speed depends on number of images and network speed
- OCR processing is CPU-intensive
- Downloads are performed sequentially to avoid overwhelming servers
- Typical processing: ~1-2 seconds per record with images

## Dependencies

- `requests` - HTTP client for downloading images
- `Pillow` - Image processing and validation
- `pytesseract` - OCR text extraction
- `pathlib` - Path handling (built-in)
- `json` - JSON processing (built-in)
- `logging` - Logging framework (built-in)

## License

This project is part of the bug reports classification system.
