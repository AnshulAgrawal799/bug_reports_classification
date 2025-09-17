#!/usr/bin/env python3
"""
run_pipeline.py

Fully autonomous image categorization pipeline that processes Firebase export JSON
and produces categorized output with downloaded images.

Usage:
    python run_pipeline.py [--input INPUT_FILE] [--output OUTPUT_FILE] [--verbose] [--dry-run]

Features:
- Downloads images from Firebase Storage URLs
- Performs OCR on downloaded images
- Categorizes images using intelligent heuristics
- Produces final JSON with all records categorized
- Comprehensive error handling and logging
"""

import argparse
import json
import logging
import hashlib
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse
import requests
from PIL import Image
import pytesseract

# New taxonomy mapping rules
from pipeline.mapping_rules import categorize_record as categorize_with_rules
from pipeline.mapping_rules import allow_unclear_label
from pipeline.predictor import load_default_predictor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ImageCategorizationPipeline:
    """Autonomous image categorization pipeline."""
    
    def __init__(self, input_file: Path, output_file: Path, screenshots_dir: Path, dry_run: bool = False):
        self.input_file = input_file
        self.output_file = output_file
        self.screenshots_dir = screenshots_dir
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        
        # Statistics
        self.stats = {
            'total_records': 0,
            'records_processed': 0,
            'images_downloaded': 0,
            'download_failures': 0,
            'categorization_successes': 0,
            'fallback_categorizations': 0
        }
        # Optional model predictor
        self.predictor = load_default_predictor()
    
    def extract_filename_from_url(self, url: str) -> str:
        """Extract deterministic filename from Firebase Storage URL."""
        try:
            parsed = urlparse(url)
            path = parsed.path
            
            # Get the last segment and decode
            last_segment = path.rsplit('/', 1)[-1]
            decoded = unquote(last_segment)
            
            # Handle folder prefixes like 'bug_reports%2F'
            if '%2F' in last_segment:
                decoded = unquote(last_segment)
            if '/' in decoded:
                decoded = decoded.rsplit('/', 1)[-1]
            
            # Remove query parameters
            if '?' in decoded:
                decoded = decoded.split('?', 1)[0]
            
            # Generate deterministic filename if original is problematic
            if not decoded or len(decoded) < 3:
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                decoded = f"image_{url_hash}.jpg"
            
            return decoded
        except Exception as e:
            logger.warning(f"Failed to extract filename from URL {url}: {e}")
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            return f"image_{url_hash}.jpg"
    
    def download_image(self, url: str, filename: str) -> bool:
        """Download image from URL to screenshots directory."""
        try:
            file_path = self.screenshots_dir / filename
            
            # Skip if already exists
            if file_path.exists():
                logger.debug(f"Image already exists: {filename}")
                return True
            
            if self.dry_run:
                logger.info(f"[DRY RUN] Would download: {url} -> {filename}")
                return True
            
            logger.info(f"Downloading: {url} -> {filename}")
            
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Validate content type
            content_type = response.headers.get('content-type', '').lower()
            if not any(img_type in content_type for img_type in ['image/', 'application/octet-stream']):
                logger.warning(f"Unexpected content type for {url}: {content_type}")
            
            # Write file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Validate downloaded file
            try:
                with Image.open(file_path) as img:
                    img.verify()
                logger.debug(f"Successfully downloaded and validated: {filename}")
                self.stats['images_downloaded'] += 1
                return True
            except Exception as e:
                logger.error(f"Downloaded file is not a valid image: {filename} - {e}")
                file_path.unlink(missing_ok=True)
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error downloading {url}: {e}")
            self.stats['download_failures'] += 1
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            self.stats['download_failures'] += 1
            return False
    
    def perform_ocr(self, image_path: Path) -> str:
        """Perform OCR on image and return extracted text."""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Perform OCR
                text = pytesseract.image_to_string(img, config='--psm 6')
                return text.strip()
        except Exception as e:
            logger.warning(f"OCR failed for {image_path}: {e}")
            return ""
    
    # Old, screen-focused categorization removed. We will use mapping_rules.categorize_record
    
    def categorize_record(self, record_id: str, record: Dict) -> str:
        """Categorize a single record using deterministic mapping rules (problem-focused taxonomy)."""
        attachments = record.get('attachments', []) or []

        ocr_texts: List[str] = []
        filenames: List[str] = []

        for url in attachments:
            filename = self.extract_filename_from_url(url)
            filenames.append(filename)
            image_path = self.screenshots_dir / filename
            if image_path.exists():
                ocr_texts.append(self.perform_ocr(image_path))

        # Optional model prediction
        model_pred: Optional[str] = None
        if self.predictor and self.predictor.is_ready():
            model_pred = self.predictor.predict(
                record.get('comment', ''), ocr_texts=ocr_texts, filenames=filenames
            )

        category = categorize_with_rules(record, ocr_texts=ocr_texts, filenames=filenames, model_pred=model_pred)
        if category:
            logger.debug(f"Categorized {record_id} -> {category}")
            self.stats['categorization_successes'] += 1
            return category

        # Fallback
        # As a safety net, only allow 'unclear_insufficient_info' if no usable content exists
        if allow_unclear_label(record, ocr_texts=ocr_texts, filenames=filenames):
            logger.debug(f"Fallback categorization for {record_id}: unclear_insufficient_info")
            self.stats['fallback_categorizations'] += 1
            return "unclear_insufficient_info"
        # If usable content exists but no category chosen, prefer model prediction or generic functional_errors
        self.stats['fallback_categorizations'] += 1
        return model_pred or "functional_errors"
    
    def process_record(self, record_id: str, record: Dict) -> Dict:
        """Process a single record: download images and categorize."""
        logger.info(f"Processing record: {record_id}")
        
        # Download images first
        attachments = record.get('attachments', []) or []
        for url in attachments:
            filename = self.extract_filename_from_url(url)
            self.download_image(url, filename)
        
        # Categorize the record
        category = self.categorize_record(record_id, record)
        
        # Update record with category
        updated_record = record.copy()
        updated_record['category'] = category
        
        self.stats['records_processed'] += 1
        return updated_record
    
    def run(self) -> bool:
        """Run the complete pipeline."""
        logger.info("=== STARTING AUTONOMOUS IMAGE CATEGORIZATION PIPELINE ===")
        logger.info(f"Input file: {self.input_file}")
        logger.info(f"Output file: {self.output_file}")
        logger.info(f"Screenshots directory: {self.screenshots_dir}")
        logger.info(f"Dry run: {self.dry_run}")
        
        try:
            # Create screenshots directory
            if not self.dry_run:
                self.screenshots_dir.mkdir(exist_ok=True)
            
            # Load input JSON
            logger.info("Loading input JSON file...")
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.stats['total_records'] = len(data)
            logger.info(f"Loaded {self.stats['total_records']} records")
            
            # Process each record
            processed_data = {}
            for record_id, record in data.items():
                try:
                    processed_record = self.process_record(record_id, record)
                    processed_data[record_id] = processed_record
                except Exception as e:
                    logger.error(f"Error processing record {record_id}: {e}")
                    # Ensure even failed records get a category while respecting strict unclear criteria
                    failed_record = record.copy()
                    try:
                        # Reconstruct minimal signals for decision
                        attachments = record.get('attachments', []) or []
                        ocr_texts: List[str] = []
                        filenames: List[str] = []
                        for url in attachments:
                            filename = self.extract_filename_from_url(url)
                            filenames.append(filename)
                        # No OCR on exception path; rely on filenames and comment
                        if allow_unclear_label(record, ocr_texts=ocr_texts, filenames=filenames):
                            failed_record['category'] = "unclear_insufficient_info"
                        else:
                            failed_record['category'] = "functional_errors"
                    except Exception:
                        # Last-resort fallback
                        failed_record['category'] = "unclear_insufficient_info"
                    processed_data[record_id] = failed_record
                    self.stats['records_processed'] += 1
            
            # Save output
            if not self.dry_run:
                logger.info(f"Saving output to: {self.output_file}")
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    json.dump(processed_data, f, ensure_ascii=False, indent=2)
            else:
                logger.info("[DRY RUN] Would save processed data to output file")
            
            # Print statistics
            self.print_statistics()
            
            logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")
            return True
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return False
    
    def print_statistics(self):
        """Print pipeline execution statistics."""
        logger.info("\n=== PIPELINE STATISTICS ===")
        logger.info(f"Total records: {self.stats['total_records']}")
        logger.info(f"Records processed: {self.stats['records_processed']}")
        logger.info(f"Images downloaded: {self.stats['images_downloaded']}")
        logger.info(f"Download failures: {self.stats['download_failures']}")
        logger.info(f"Successful categorizations: {self.stats['categorization_successes']}")
        logger.info(f"Fallback categorizations: {self.stats['fallback_categorizations']}")
        
        if self.stats['total_records'] > 0:
            success_rate = (self.stats['records_processed'] / self.stats['total_records']) * 100
            logger.info(f"Processing success rate: {success_rate:.1f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Autonomous image categorization pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--input', type=Path, 
                       default='signintest-84632-default-rtdb-active-export.json',
                       help='Input JSON file (default: signintest-84632-default-rtdb-active-export.json)')
    parser.add_argument('--output', type=Path, default='final_output.json',
                       help='Output JSON file (default: final_output.json)')
    parser.add_argument('--screenshots-dir', type=Path, default='input_screenshots',
                       help='Directory for downloaded screenshots (default: input_screenshots)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate input file
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        sys.exit(1)
    
    # Create and run pipeline
    pipeline = ImageCategorizationPipeline(
        input_file=args.input,
        output_file=args.output,
        screenshots_dir=args.screenshots_dir,
        dry_run=args.dry_run
    )
    
    success = pipeline.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
