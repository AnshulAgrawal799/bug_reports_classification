#!/usr/bin/env python3
"""
run_full_best_pipeline.py

Single-entry pipeline that performs the entire categorization process in one run and writes
only the final consolidated output to final_best_output.json (no intermediate files).

Steps (in-memory):
1) Load input Firebase export JSON (id -> record)
2) For each record:
   - Download attachments to input_screenshots/
   - OCR images
   - Detect language, translate comment if needed
   - Optional model prediction (if model is present)
   - Categorize using rules (mapping_rules.categorize_record_with_meta)
   - Store enriched fields (category, label_confidence, label_reason, extracted_text, translations)
3) Relabel pass ("relab" logic) over the in-memory results using latest rules, keywords, and predictor
   - Recompute/confirm category using the enriched fields without writing any intermediate file
4) Write the final consolidated result to final_best_output.json

Usage:
  python run_full_best_pipeline.py \
      [--input signintest-84632-default-rtdb-active-export.json] \
      [--output final_best_output.json] \
      [--screenshots-dir input_screenshots] \
      [--verbose]

Notes:
- Requires Pillow, pytesseract, requests
- Optionally uses models from models/ if present (bug_classifier.joblib, bug_vectorizer.joblib)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from PIL import Image
import pytesseract

# Project modules
from pipeline.mapping_rules import (
    categorize_record_with_meta,
    allow_unclear_label,
)
from pipeline.predictor import load_default_predictor
from pipeline.translation import detect_and_translate


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


# -----------------------------
# Helpers for attachments/OCR
# -----------------------------
class DownloaderOCR:
    def __init__(self, screenshots_dir: Path):
        self.screenshots_dir = screenshots_dir
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    @staticmethod
    def extract_filename_from_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            path = parsed.path
            last_segment = path.rsplit('/', 1)[-1]
            decoded = unquote(last_segment)
            if '%2F' in last_segment:
                decoded = unquote(last_segment)
            if '/' in decoded:
                decoded = decoded.rsplit('/', 1)[-1]
            if '?' in decoded:
                decoded = decoded.split('?', 1)[0]
            if not decoded or len(decoded) < 3:
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                decoded = f"image_{url_hash}.jpg"
            return decoded
        except Exception as e:
            logger.warning(f"Failed to extract filename from URL {url}: {e}")
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            return f"image_{url_hash}.jpg"

    def download_image(self, url: str, filename: str) -> bool:
        try:
            file_path = self.screenshots_dir / filename
            if file_path.exists():
                return True
            logger.debug(f"Downloading: {url} -> {filename}")
            resp = self.session.get(url, timeout=30, stream=True)
            resp.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            # validate
            try:
                with Image.open(file_path) as img:
                    img.verify()
                return True
            except Exception as e:
                logger.error(f"Downloaded file is not a valid image: {filename} - {e}")
                file_path.unlink(missing_ok=True)
                return False
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return False

    @staticmethod
    def perform_ocr(image_path: Path) -> str:
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                text = pytesseract.image_to_string(img, config='--psm 6')
                return (text or '').strip()
        except Exception as e:
            logger.debug(f"OCR failed for {image_path}: {e}")
            return ""


# --------------------------------------------------
# First-pass processing (download, OCR, translate, categorize)
# --------------------------------------------------

def first_pass(
    data: Dict[str, Dict[str, Any]],
    screenshots_dir: Path,
    predictor
) -> Dict[str, Dict[str, Any]]:
    do = DownloaderOCR(screenshots_dir)
    out: Dict[str, Dict[str, Any]] = {}

    for rec_id, record in data.items():
        try:
            attachments = record.get('attachments', []) or []
            filenames: List[str] = []
            ocr_texts: List[str] = []
            for url in attachments:
                if not isinstance(url, str):
                    continue
                fname = do.extract_filename_from_url(url)
                filenames.append(fname)
                if do.download_image(url, fname):
                    img_path = screenshots_dir / fname
                    if img_path.exists():
                        ocr_texts.append(do.perform_ocr(img_path))

            # language detection + translation
            original_comment: str = record.get('comment', '') or ''
            translated_comment, detected_lang = detect_and_translate(original_comment)
            effective_record = dict(record)
            if translated_comment:
                effective_record['comment'] = translated_comment

            # optional model pred
            model_pred: Optional[str] = None
            if predictor and predictor.is_ready():
                record_for_pred = dict(effective_record)
                if translated_comment:
                    record_for_pred['comment_translated'] = translated_comment
                model_pred = predictor.predict_from_record(record_for_pred, ocr_texts=ocr_texts, filenames=filenames)

            # rules-based categorization
            category, confidence, reason = categorize_record_with_meta(
                effective_record, ocr_texts=ocr_texts, filenames=filenames, model_pred=model_pred
            )

            updated = dict(record)
            updated['category'] = category
            updated['label_confidence'] = round(float(confidence), 2)
            updated['label_reason'] = reason
            updated['extracted_text'] = "\n\n".join([t for t in ocr_texts if t]) if any(ocr_texts) else ""
            if detected_lang and detected_lang != 'en' and translated_comment:
                updated['detected_lang'] = detected_lang
                updated['comment_translated'] = translated_comment

            out[rec_id] = updated
        except Exception as e:
            logger.error(f"Error processing record {rec_id}: {e}")
            # Ensure category present with strict unclear gate
            try:
                attachments = record.get('attachments', []) or []
                filenames: List[str] = []
                for url in attachments:
                    if not isinstance(url, str):
                        continue
                    fname = DownloaderOCR.extract_filename_from_url(url)
                    filenames.append(fname)
                if allow_unclear_label(record, ocr_texts=[], filenames=filenames):
                    record['category'] = 'unclear_insufficient_info'
                else:
                    record['category'] = 'functional_errors'
            except Exception:
                record['category'] = 'unclear_insufficient_info'
            out[rec_id] = record

    return out


# --------------------------------------------------
# In-memory relabel pass (mirror of scripts/relabel_with_rules without I/O)
# --------------------------------------------------

def _collect_ocr_texts_from_record(rec: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    if isinstance(rec.get('extracted_text'), str):
        if rec['extracted_text']:
            texts.append(rec['extracted_text'])
    elif isinstance(rec.get('extracted_text'), list):
        texts.extend([t for t in rec['extracted_text'] if isinstance(t, str) and t])
    return texts


def _collect_filenames_from_record(rec: Dict[str, Any]) -> List[str]:
    fns: List[str] = []
    atts = rec.get('attachments') or []
    if isinstance(atts, list):
        for url in atts:
            if not isinstance(url, str):
                continue
            name = url.rsplit('/', 1)[-1]
            name = name.split('?', 1)[0]
            fns.append(name)
    return fns


def relabel_in_memory(
    processed: Dict[str, Dict[str, Any]],
    predictor
) -> Dict[str, Dict[str, Any]]:
    for rec_id, rec in processed.items():
        try:
            ocr_texts = _collect_ocr_texts_from_record(rec)
            filenames = _collect_filenames_from_record(rec)

            original_comment: str = rec.get('comment', '') or ''
            translated_comment, detected_lang = detect_and_translate(original_comment)
            if translated_comment:
                rec['comment_translated'] = translated_comment

            model_pred: Optional[str] = None
            if predictor and predictor.is_ready():
                record_for_pred = dict(rec)
                if rec.get('comment_translated'):
                    record_for_pred['comment_translated'] = rec['comment_translated']
                model_pred = predictor.predict_from_record(record_for_pred, ocr_texts=ocr_texts, filenames=filenames)

            new_cat, conf, reason = categorize_record_with_meta(rec, ocr_texts=ocr_texts, filenames=filenames, model_pred=model_pred)
            rec['category'] = new_cat
            rec['label_confidence'] = max(float(rec.get('label_confidence') or 0.0), float(conf))
            rec['label_reason'] = reason
            if detected_lang and detected_lang != 'en' and translated_comment:
                rec['detected_lang'] = detected_lang
        except Exception as e:
            logger.debug(f"Relabel step failed for {rec_id}: {e}")
            # keep first-pass result
            continue
    return processed


# -----------------------------
# Main
# -----------------------------

def main():
    parser = argparse.ArgumentParser(description='Run full best pipeline in a single pass')
    parser.add_argument('--input', type=Path, default=Path('signintest-84632-default-rtdb-active-export.json'))
    parser.add_argument('--output', type=Path, default=Path('final_best_output.json'))
    parser.add_argument('--screenshots-dir', type=Path, default=Path('input_screenshots'))
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        raise SystemExit(1)

    args.screenshots_dir.mkdir(exist_ok=True)

    logger.info('Loading input JSON...')
    data: Dict[str, Dict[str, Any]] = json.loads(args.input.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        logger.error('Input JSON must be an object keyed by record IDs')
        raise SystemExit(1)

    predictor = load_default_predictor()  # may be None

    logger.info('First pass: download, OCR, translate, categorize...')
    first = first_pass(data, args.screenshots_dir, predictor)

    logger.info('Relabel pass: applying latest rules and model adjustments in-memory...')
    final = relabel_in_memory(first, predictor)

    logger.info(f'Saving final consolidated output to: {args.output}')
    args.output.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')

    logger.info('Done.')


if __name__ == '__main__':
    main()
