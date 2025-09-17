#!/usr/bin/env python3
"""
predictor.py

Lightweight text-based classifier wrapper for bug report categories.
- Uses scikit-learn TF-IDF + LinearSVC (or any sklearn-compatible classifier)
- Predicts a canonical category id from `config/categories.json`
- Exposes a simple API for the pipeline

Model artifacts default path:
  models/bug_classifier.joblib
  models/bug_vectorizer.joblib

Training is performed by scripts/train_model.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import joblib

DEFAULT_MODELS_DIR = Path('models')
DEFAULT_MODEL_PATH = DEFAULT_MODELS_DIR / 'bug_classifier.joblib'
DEFAULT_VECTORIZER_PATH = DEFAULT_MODELS_DIR / 'bug_vectorizer.joblib'


class BugPredictor:
    def __init__(self, model_path: Path, vectorizer_path: Path):
        self.model_path = Path(model_path)
        self.vectorizer_path = Path(vectorizer_path)
        self.model = None
        self.vectorizer = None

    def load(self) -> bool:
        try:
            self.model = joblib.load(self.model_path)
            self.vectorizer = joblib.load(self.vectorizer_path)
            return True
        except Exception:
            return False

    def is_ready(self) -> bool:
        return self.model is not None and self.vectorizer is not None

    @staticmethod
    def _make_text(comment: str, ocr_texts: List[str], filenames: List[str]) -> str:
        comment = (comment or '').strip()
        ocr_blob = ' '.join(t for t in (ocr_texts or []) if t)
        fname_blob = ' '.join(f for f in (filenames or []) if f)
        return ' '.join([comment, ocr_blob, fname_blob]).strip()

    def predict(self, comment: str, ocr_texts: List[str], filenames: List[str]) -> Optional[str]:
        if not self.is_ready():
            return None
        text = self._make_text(comment, ocr_texts, filenames)
        if not text:
            return None
        X = self.vectorizer.transform([text])
        try:
            pred = self.model.predict(X)[0]
            return str(pred)
        except Exception:
            return None


def load_default_predictor() -> Optional[BugPredictor]:
    predictor = BugPredictor(DEFAULT_MODEL_PATH, DEFAULT_VECTORIZER_PATH)
    if predictor.load():
        return predictor
    return None
