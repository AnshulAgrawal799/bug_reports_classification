#!/usr/bin/env python3
"""
mapping_rules.py

Deterministic heuristics to map bug reports to canonical, problem-focused taxonomy.

Taxonomy (loaded externally from config/categories.json):
- functional_errors
- ui_ux_issues
- performance_issues
- connectivity_problems
- authentication_access
- data_integrity_issues
- crash_stability
- integration_failures
- configuration_settings
- compatibility_issues
- feature_requests
- unclear_insufficient_info

Usage:
    from pipeline.mapping_rules import categorize_record
    cat = categorize_record(record, ocr_texts=[...], filenames=[...])

Notes:
- Heuristics are deterministic and order-sensitive; the first matching rule wins.
- Designed to be run pre/post model inference; you can feed model_pred and it will
  correct/override based on high-confidence rules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import re
import json

# Load canonical categories from config for validation (optional at runtime)
_CATEGORIES_PATH = Path(__file__).resolve().parents[1] / 'config' / 'categories.json'
try:
    with open(_CATEGORIES_PATH, 'r', encoding='utf-8') as f:
        _CANONICAL_CATEGORIES = {item['id'] for item in json.load(f)}
except Exception:
    _CANONICAL_CATEGORIES = {
        'functional_errors', 'ui_ux_issues', 'performance_issues', 'connectivity_problems',
        'authentication_access', 'data_integrity_issues', 'crash_stability', 'integration_failures',
        'configuration_settings', 'compatibility_issues', 'feature_requests', 'unclear_insufficient_info'
    }


def _norm(s: str) -> str:
    return (s or '').strip().lower()


def _match_any(text: str, keywords: List[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in keywords)


def _regex_any(text: str, patterns: List[str]) -> bool:
    t = _norm(text)
    return any(re.search(p, t) for p in patterns)


def _has_usable_content(comment: str, ocr_texts: Optional[List[str]], filenames: Optional[List[str]], log_filename: Optional[str] = None) -> bool:
    """
    Determine whether the record contains any usable signal that should force a
    best-effort categorization instead of returning 'unclear_insufficient_info'.

    Usable content includes any of the following (case-insensitive):
    - Alphanumeric text with meaningful length (>= 10 chars)
    - Presence of digits/numbers
    - Dates or times (e.g., 12/01/2024, 12-01-24, 14:35)
    - Currency tokens or amounts (₹, rs, inr, amount, total, balance)
    - Key-value like fields ("label: value")
    - Recognizable headers/keywords (date, time, settings, login, error, network, otp, password, invoice)
    - Filenames that contain indicative words (login, signin, error, timeout, network)
    """
    texts: List[str] = []
    t_comment = _norm(comment)
    if t_comment:
        texts.append(t_comment)
    for t in (ocr_texts or []):
        if t:
            texts.append(_norm(t))
    combined = " \n ".join(texts)

    # If there's substantial text, it's usable
    if len(combined) >= 10:
        return True

    # Numeric, dates, times
    if re.search(r"\d", combined):
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", combined):
        return True
    if re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", combined):
        return True

    # Currency/amount semantics
    header_keywords = ["date", "time", "invoice", "total", "amount", "balance", "settings",
                       "login", "sign in", "signin", "password", "otp", "error", "failed", "network"]
    currency_tokens = [r"\b(rs|inr)\b", r"₹", r"\bamount\b", r"\btotal\b", r"\bbalance\b"]
    if any(k in combined for k in header_keywords):
        return True
    if any(re.search(p, combined) for p in currency_tokens):
        return True

    # Key-value fields like "Amount: 120"
    if re.search(r"\b[a-z][a-z0-9_\s]{2,}:\s*\S+", combined):
        return True

    # Filenames containing hints or structured info also count as usable content
    candidate_filenames: List[str] = list(filenames or [])
    if log_filename:
        candidate_filenames.append(log_filename)
    for fn in candidate_filenames:
        f = _norm(fn)
        if not f:
            continue
        # Indicative keywords
        if any(k in f for k in ["login", "signin", "error", "timeout", "network"]):
            return True
        # Dates/times or digits in filenames
        if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", f) or re.search(r"\d", f):
            return True
        # Log or text evidence
        if f.endswith('.txt') or f.endswith('.log'):
            return True

    return False


def allow_unclear_label(record: Dict, ocr_texts: Optional[List[str]] = None, filenames: Optional[List[str]] = None) -> bool:
    """
    Return True ONLY if it's acceptable to label as 'unclear_insufficient_info'.
    That is, when there is no usable content to guide categorization.
    """
    comment = _norm(record.get('comment', ''))
    # Derive a log filename from record if available
    log_url = _norm((record or {}).get('logFile', ''))
    log_filename: Optional[str] = None
    if log_url:
        # Extract last path segment
        log_filename = log_url.rsplit('/', 1)[-1].split('?', 1)[0]
    return not _has_usable_content(comment, ocr_texts, filenames, log_filename=log_filename)


def categorize_from_comment(comment: str) -> Optional[str]:
    t = _norm(comment)
    if not t:
        return None

    # Feature requests
    if _match_any(t, ['feature request', 'feature', 'would be great', 'please add', 'enhancement']):
        return 'feature_requests'

    # Connectivity
    if _match_any(t, ['unable to connect', 'no internet', 'network error', 'api failed', 'server error', 'timeout']):
        return 'connectivity_problems'

    # Authentication & Access
    if _match_any(t, ['login', 'sign in', 'authentication', 'password', 'otp', 'permission denied', 'access denied', 'session']):
        return 'authentication_access'

    # Performance
    if _match_any(t, ['slow', 'lag', 'freeze', 'freezes', 'hanging', 'loading forever', 'takes too long', 'sluggish']):
        return 'performance_issues'

    # Crash & Stability
    if _match_any(t, ['crash', 'crashes', 'force close', 'stopped working', 'app closed unexpectedly']):
        return 'crash_stability'

    # Integration (prioritize over generic "fails")
    if _match_any(t, ['printer', 'bluetooth', 'weighing scale', 'payment gateway', 'google', 'firebase', 'upi', 'razorpay']):
        return 'integration_failures'

    # Configuration (prioritize over generic data issues)
    if _match_any(t, ['settings', 'configuration', 'preference', 'does not save setting', 'default value wrong']):
        return 'configuration_settings'

    # Data integrity
    if _match_any(t, ['wrong total', 'incorrect', 'mismatch', 'duplicate', 'missing data', 'data lost', 'not saved']):
        return 'data_integrity_issues'

    # UI/UX
    if _match_any(t, ['ui', 'ux', 'alignment', 'overlap', 'cut off', 'hard to read', 'too small', 'button not visible']):
        return 'ui_ux_issues'

    # Functional errors
    if _match_any(t, ['does not work', 'not working', 'cannot', "can't", 'fails', 'not possible', 'broken', 'stuck action']):
        return 'functional_errors'

    # Compatibility
    if _match_any(t, ['only on my phone', 'android 14', 'ios', 'tablet', 'resolution', 'screen size']):
        return 'compatibility_issues'

    return None


def categorize_from_ocr(ocr_text: str) -> Optional[str]:
    t = _norm(ocr_text)
    if not t:
        return None

    # Explicit crash/error indicators
    if _match_any(t, ['error', 'exception', 'fatal', 'stack trace']):
        return 'functional_errors'

    # Auth indicators on screen
    if _match_any(t, ['sign in', 'login', 'password', 'otp']):
        return 'authentication_access'

    # Network/API indicators
    if _match_any(t, ['unable to connect', 'no internet', 'network error', 'api request failed', 'timeout']):
        return 'connectivity_problems'

    # Performance indicators
    if _match_any(t, ['loading', 'please wait', 'processing']) and not _match_any(t, ['success', 'completed']):
        return 'performance_issues'

    # Configuration/settings screens
    if _match_any(t, ['settings', 'preferences', 'configuration']):
        return 'configuration_settings'

    # Payment/integration words
    if _match_any(t, ['payment', 'transaction', 'gateway', 'upi', 'printer', 'bluetooth']):
        return 'integration_failures'

    # Data integrity clues
    if _match_any(t, ['total', 'balance', 'amount']) and _match_any(t, ['wrong', 'mismatch', 'not matching']):
        return 'data_integrity_issues'

    return None


def categorize_from_filename(filename: str) -> Optional[str]:
    f = _norm(filename)
    if not f:
        return None

    # Crash dump / log files
    if f.endswith('.txt') or f.endswith('.log'):
        # Do not force an 'unclear' label based solely on presence of logs.
        # Let comment/OCR/model determine a best-effort category.
        return None

    # Heuristic hints from names
    if 'screenshot' in f and 'error' in f:
        return 'functional_errors'
    if 'login' in f or 'signin' in f:
        return 'authentication_access'
    if 'timeout' in f or 'network' in f:
        return 'connectivity_problems'

    return None


def post_adjustment(model_pred: Optional[str], signals: Dict[str, bool]) -> Optional[str]:
    """
    Optional post-inference adjustment rules. Example: if model says UI but we see crash keywords,
    upgrade to crash_stability.
    """
    pred = model_pred
    if signals.get('explicit_crash'):
        return 'crash_stability'
    if signals.get('explicit_connectivity'):
        return 'connectivity_problems'
    if signals.get('explicit_auth') and pred in {None, 'ui_ux_issues', 'unclear_insufficient_info'}:
        return 'authentication_access'
    return pred


def categorize_record(record: Dict, ocr_texts: Optional[List[str]] = None, filenames: Optional[List[str]] = None, model_pred: Optional[str] = None) -> str:
    """
    Determine the best category for a record using deterministic heuristics.
    Priority order:
      1) Strong comment-based rules
      2) Strong OCR-based rules
      3) Strong filename-based rules
      4) Post-adjustment overrides
      5) Fallback to unclear_insufficient_info
    """
    comment = _norm(record.get('comment', ''))

    # 1) Comment
    c = categorize_from_comment(comment)
    if c:
        return c

    # 2) OCR
    if ocr_texts:
        for t in ocr_texts:
            cat = categorize_from_ocr(t)
            if cat:
                return cat

    # 3) Filename
    if filenames:
        for fn in filenames:
            cat = categorize_from_filename(fn)
            if cat:
                return cat

    # 4) Post-adjustment
    signals = {
        'explicit_crash': _match_any(comment, ['crash', 'force close', 'stopped working']),
        'explicit_connectivity': _match_any(comment, ['unable to connect', 'network error', 'api failed', 'timeout']),
        'explicit_auth': _match_any(comment, ['login', 'sign in', 'password', 'otp'])
    }
    adjusted = post_adjustment(model_pred, signals)
    if adjusted:
        return adjusted

    # 4.5) Weak-signal, best-effort mapping before giving up
    # Combine available texts for lightweight heuristics
    combined_texts: List[str] = []
    comment = _norm(record.get('comment', ''))
    if comment:
        combined_texts.append(comment)
    for t in (ocr_texts or []):
        if t:
            combined_texts.append(_norm(t))

    combined = ' \n '.join(combined_texts)

    if combined:
        # Numeric/currency hints -> data integrity issues
        currency_patterns = [r"\b(rs|inr|₹)\b", r"\bamount\b", r"\btotal\b", r"\bbalance\b", r"\bcoins?\b"]
        number_present = bool(re.search(r"\d", combined))
        currency_present = any(re.search(p, combined) for p in currency_patterns)
        mismatch_words = ["wrong", "mismatch", "not matching", "less", "more", "only", "difference"]
        if (number_present and currency_present) or _match_any(combined, mismatch_words):
            return 'data_integrity_issues'

        # Generic error/functionality hints
        generic_error_hints = ["error", "fail", "failed", "not working", "does not work", "unable", "stuck", "cannot", "can't"]
        if _match_any(combined, generic_error_hints):
            return 'functional_errors'

        # Connectivity weaker hints
        weak_connectivity = ["no internet", "network", "server", "timeout", "api"]
        if _match_any(combined, weak_connectivity):
            return 'connectivity_problems'

        # Auth weaker hints
        weak_auth = ["otp", "signin", "sign in", "login", "password", "pin"]
        if _match_any(combined, weak_auth):
            return 'authentication_access'

    # 4.8) If model has a prediction, prefer it over unclear
    if model_pred and model_pred != 'unclear_insufficient_info':
        return model_pred

    # 5) Final decision with strict unclear gate
    if allow_unclear_label(record, ocr_texts=ocr_texts, filenames=filenames):
        return 'unclear_insufficient_info'

    # If we reach here, there is usable content but no strong/weak match.
    # Prefer model prediction if any; otherwise default to a generic, action-oriented class.
    if model_pred:
        return model_pred
    return 'functional_errors'


__all__ = [
    'categorize_record',
    'categorize_from_comment',
    'categorize_from_ocr',
    'categorize_from_filename',
    'post_adjustment',
    'allow_unclear_label'
]
