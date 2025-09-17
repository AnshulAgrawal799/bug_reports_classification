#!/usr/bin/env python3
"""
train_model.py

Train a lightweight text classifier for bug report categories using the
canonical taxonomy in `config/categories.json`.

Expected input:
  - A CSV file with columns: `text`, `category`
    - `text`: concatenated report text features (e.g., comment + OCR + filename)
    - `category`: canonical category id (e.g., functional_errors)

Outputs (default: models/):
  - bug_classifier.joblib
  - bug_vectorizer.joblib

Examples:
  python scripts/train_model.py --train data/train.csv
  python scripts/train_model.py --train data/train.csv --models_dir models

Tip: Use scripts/relabel_dataset.py to map old labels to the canonical ids.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

DEFAULT_MODELS_DIR = Path('models')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', type=Path, required=True, help='Training CSV with columns: text, category')
    ap.add_argument('--models_dir', type=Path, default=DEFAULT_MODELS_DIR)
    ap.add_argument('--test_size', type=float, default=0.2)
    ap.add_argument('--random_state', type=int, default=42)
    ap.add_argument('--min_samples_per_class', type=int, default=1,
                    help='If >1, remap labels with fewer than this many samples to "unclear_insufficient_info" before splitting.')
    args = ap.parse_args()

    args.models_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.train)
    if 'text' not in df.columns or 'category' not in df.columns:
        raise SystemExit("Training CSV must have 'text' and 'category' columns")

    X = df['text'].astype(str).fillna('')
    y = df['category'].astype(str).fillna('unclear_insufficient_info')

    # Optionally remap rare classes to the fallback category to stabilize training/eval
    if args.min_samples_per_class and args.min_samples_per_class > 1:
        counts = y.value_counts()
        rare_labels = counts[counts < args.min_samples_per_class].index.tolist()
        if rare_labels:
            print(f"[info] Remapping {len(rare_labels)} rare labels (<{args.min_samples_per_class} samples) to 'unclear_insufficient_info': {rare_labels}")
            y = y.where(~y.isin(rare_labels), other='unclear_insufficient_info')
    
    # Prefer stratified split, but handle edge cases where some classes have < 2 samples.
    # In such cases, sklearn raises: "The least populated class in y has only 1 member..."
    use_stratify = True
    try:
        # Quick check to avoid a known error condition
        class_counts = y.value_counts()
        if class_counts.min() < 2 or y.nunique() < 2:
            use_stratify = False
        if use_stratify:
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=args.test_size, random_state=args.random_state, stratify=y
            )
        else:
            print("[warn] Stratified split disabled: some classes have <2 samples. Falling back to non-stratified split.")
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=args.test_size, random_state=args.random_state, stratify=None
            )
    except ValueError as e:
        # Fallback: train on all data and skip validation/report
        print(f"[warn] Stratified split failed: {e}\n[warn] Training on full dataset and skipping validation.")
        X_train, y_train = X, y
        X_val, y_val = X.iloc[0:0], y.iloc[0:0]

    # Build pipeline
    pipe: Pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1,2), min_df=2, max_features=20000)),
        ('clf', LinearSVC()),
    ])

    pipe.fit(X_train, y_train)

    if len(X_val) > 0:
        y_pred = pipe.predict(X_val)
        print(classification_report(y_val, y_pred, zero_division=0))
    else:
        print("[info] No validation split available; skipped classification report.")

    # Save separate artifacts for predictor wrapper
    tfidf: TfidfVectorizer = pipe.named_steps['tfidf']
    clf: LinearSVC = pipe.named_steps['clf']

    joblib.dump(clf, args.models_dir / 'bug_classifier.joblib')
    joblib.dump(tfidf, args.models_dir / 'bug_vectorizer.joblib')

    print(f"Saved model -> {args.models_dir / 'bug_classifier.joblib'}")
    print(f"Saved vectorizer -> {args.models_dir / 'bug_vectorizer.joblib'}")


if __name__ == '__main__':
    main()
