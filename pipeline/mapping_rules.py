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
from typing import Dict, List, Optional, Tuple, Set
import re
import json
import unicodedata

# Load canonical categories from config for validation (optional at runtime)
_CATEGORIES_PATH = Path(__file__).resolve().parents[1] / 'config' / 'categories.json'
_RULES_PATH = Path(__file__).resolve().parents[1] / 'config' / 'rules.json'
try:
    with open(_CATEGORIES_PATH, 'r', encoding='utf-8') as f:
        _CANONICAL_CATEGORIES = {item['id'] for item in json.load(f)}
except Exception:
    _CANONICAL_CATEGORIES = {
        'functional_errors', 'ui_ux_issues', 'performance_issues', 'connectivity_problems',
        'authentication_access', 'data_integrity_issues', 'crash_stability', 'integration_failures',
        'configuration_settings', 'compatibility_issues', 'feature_requests', 'unclear_insufficient_info'
    }

# Load external rules (non-breaking option B)
try:
    with open(_RULES_PATH, 'r', encoding='utf-8') as f:
        _RULES = json.load(f)
        _PRIORITY_ORDER: List[str] = _RULES.get('priority_order', [])
        _KEYWORD_MAP: Dict[str, str] = _RULES.get('keyword_map', {})
        _REGEX_MAP: Dict[str, str] = _RULES.get('regex_map', {})
        _VALIDATION = _RULES.get('validation', {})
        _STRUCT_RE = _VALIDATION.get('structured_token_regex', {})
except Exception:
    _PRIORITY_ORDER = [
        'functional_errors', 'data_integrity_issues', 'integration_failures', 'connectivity_problems',
        'crash_stability', 'performance_issues', 'ui_ux_issues', 'configuration_settings',
        'authentication_access', 'compatibility_issues', 'feature_requests'
    ]
    _KEYWORD_MAP = {}
    _REGEX_MAP = {}
    _STRUCT_RE = {
        'date': r"\b\d{4}[-/]\d{2}[-/]\d{2}\b",
        'currency': r"(?:₹|\$|€)\s?\d{2,6}",
        'plain_amount': r"\b\d{2,6}\b",
        'coins_word': r"\bcoins?\b"
    }

def _normalize_text(s: str) -> str:
    """Robust normalization: lowercase, unicode NFKC, strip punctuation, collapse whitespace."""
    if not s:
        return ''
    # Unicode normalize
    s = unicodedata.normalize('NFKC', s)
    # Lowercase
    s = s.lower()
    # Approximate punctuation removal by removing non-word except currency symbols
    s = re.sub(r"[^\w\s₹$€]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm(s: str) -> str:
    return _normalize_text(s)


def _match_any(text: str, keywords: List[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in keywords)


def _regex_any(text: str, patterns: List[str]) -> bool:
    t = _norm(text)
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)


def _compile_structured_patterns() -> Dict[str, re.Pattern]:
    compiled: Dict[str, re.Pattern] = {}
    for name, pattern in (_STRUCT_RE or {}).items():
        try:
            compiled[name] = re.compile(pattern, flags=re.IGNORECASE)
        except re.error:
            # Skip invalid regex patterns
            continue
    return compiled


_STRUCT_PATTERNS = _compile_structured_patterns()


def _structured_tokens_present(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    for pat in _STRUCT_PATTERNS.values():
        if pat.search(t):
            return True
    return False


def _keyword_matches(text: str) -> Tuple[Set[str], Set[str]]:
    """Return (matched_keywords, matched_categories) using keyword_map substrings and regex_map patterns."""
    t = _norm(text)
    matched_keywords: Set[str] = set()
    matched_categories: Set[str] = set()
    if not t:
        return matched_keywords, matched_categories
    # Substring keyword_map
    for kw, cat in (_KEYWORD_MAP or {}).items():
        k = _norm(kw)
        if k and k in t:
            matched_keywords.add(kw)
            if cat:
                matched_categories.add(cat)
    # Regex regex_map
    for pat, cat in (_REGEX_MAP or {}).items():
        try:
            if re.search(pat, t, flags=re.IGNORECASE):
                matched_keywords.add(f"re:{pat}")
                if cat:
                    matched_categories.add(cat)
        except re.error:
            continue
    return matched_keywords, matched_categories


def _levenshtein_distance(a: str, b: str) -> int:
    """Compute Levenshtein distance for small tokens."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            temp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    return dp[lb]


def _fuzzy_contains(text: str, token: str, max_dist: int = 1) -> bool:
    """Heuristic fuzzy match: check if any word in text is within max_dist of token."""
    t = _norm(text)
    if not t:
        return False
    words = t.split()
    tok = _norm(token)
    if not tok:
        return False
    for w in words:
        if abs(len(w) - len(tok)) <= max_dist and _levenshtein_distance(w, tok) <= max_dist:
            return True
    return False


def _resolve_by_priority(categories: Set[str]) -> Optional[str]:
    if not categories:
        return None
    # Use configured priority order; otherwise stable sort by name
    order = {c: i for i, c in enumerate(_PRIORITY_ORDER)} if _PRIORITY_ORDER else {}
    return sorted(categories, key=lambda c: order.get(c, 10_000))[0]


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
    comment = _norm(record.get('comment_translated') or record.get('comment', ''))
    # Derive a log filename from record if available
    log_url = _norm((record or {}).get('logFile', ''))
    log_filename: Optional[str] = None
    if log_url:
        # Extract last path segment
        log_filename = log_url.rsplit('/', 1)[-1].split('?', 1)[0]
    # First check general usability
    has_usable = _has_usable_content(comment, ocr_texts, filenames, log_filename=log_filename)
    if has_usable:
        return False

    # Also gate on keyword and structured token presence per rules.json
    combined_texts: List[str] = []
    if comment:
        combined_texts.append(comment)
    for t in (ocr_texts or []):
        if t:
            combined_texts.append(_norm(t))
    combined = " \n ".join(combined_texts)

    kws, cats = _keyword_matches(combined)
    if kws or cats:
        return False
    if _structured_tokens_present(combined):
        return False
    return True


def categorize_from_comment(comment: str) -> Optional[str]:
    t = _norm(comment)
    if not t:
        return None

    # First-pass regex-based rules for frequent patterns
    # Data integrity: sales/coins/amount/balance discrepancies
    if _regex_any(t, [r"\b(sell amount|sell|coins?|amount|balance|incent|incentive)\b", r"\b(amount mismatch|wrong amount|only \d+)\b"]):
        return 'data_integrity_issues'

    # App not opening and similar
    if _regex_any(t, [r"\b(app not open|app not opening|can't open( app)?|cannot open( app)?)\b"]):
        return 'functional_errors'

    # Performance lag/slow
    if _regex_any(t, [r"\b(lag( issue)?|app lag|slow|sluggish|takes too long)\b"]):
        return 'performance_issues'

    # Connectivity issues (expand with localized phrases)
    if _regex_any(t, [
        r"\b(net( ?issue)?|network|no internet|server down|timeout)\b",
        r"\b(internet nahi|net problem|server band|network down|server nahi)\b",
        r"\b(नेट( ?समस्या)?|सर्वर डाउन|नेटवर्क समस्या)\b"
    ]):
        return 'connectivity_problems'

    # Stop notifications request -> treat as feature/config request (user requested feature_requests)
    if _regex_any(t, [r"\bstop (the )?notification(s)?\b", r"\bdisable notification(s)?\b", r"\bturn off notification(s)?\b"]):
        return 'feature_requests'

    # Rate card issues
    if _regex_any(t, [r"\brate ?card( not found| missing)?\b"]):
        return 'functional_errors'

    # Product quality issues
    if _regex_any(t, [r"\b(quality|bad quality|quality issue|damaged|damage|spoil(ed)?|waste|dented)\b"]):
        return 'product_quality_issues'

    # Feature requests
    if _match_any(t, ['feature request', 'feature', 'would be great', 'please add', 'enhancement']):
        return 'feature_requests'

    # Connectivity
    if _match_any(t, ['unable to connect', 'no internet', 'network error', 'api failed', 'server error', 'timeout']):
        return 'connectivity_problems'

    # Authentication & Access (expanded locales)
    if _match_any(t, ['login', 'sign in', 'authentication', 'password', 'otp', 'permission denied', 'access denied', 'session',
                      'pin', 'mpin', 'forgot password']) or _regex_any(t, [
        r"\b(otp nahi|otp नहीं|otp வரவில்லை|கடவுச்சொல்|पासवर्ड|लॉगिन|साइन इन)\b",
        r"\b(otp not received|otp failed|cannot login|cant login)\b"
    ]):
        return 'authentication_access'

    # Performance
    if _match_any(t, ['slow', 'lag', 'freeze', 'freezes', 'hanging', 'loading forever', 'takes too long', 'sluggish']):
        return 'performance_issues'

    # Crash & Stability
    if _match_any(t, ['crash', 'crashes', 'force close', 'stopped working', 'app closed unexpectedly']):
        return 'crash_stability'

    # Integration (prioritize over generic "fails") with localized payment terms
    if _match_any(t, ['printer', 'bluetooth', 'weighing scale', 'payment gateway', 'google', 'firebase', 'upi', 'razorpay', 'gateway', 'transaction failed']) or _regex_any(t, [
        r"\b(bhim|phonepe|gpay|paytm|tez)\b",
        r"\b(upi fail(ed)?|payment fail(ed)?|payment pending|gateway error)\b",
        r"\b(यूपीआई|भुगतान|पेमेंट)\b"
    ]):
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

    # Apply first-pass rules here too for OCR text
    if _regex_any(t, [r"\b(app not open|app not opening|can't open( app)?|cannot open( app)?)\b"]):
        return 'functional_errors'
    if _regex_any(t, [r"\b(lag( issue)?|app lag|slow|sluggish|takes too long)\b"]):
        return 'performance_issues'
    if _regex_any(t, [r"\b(net( ?issue)?|network|no internet|server down|timeout)\b"]):
        return 'connectivity_problems'
    if _regex_any(t, [r"\brate ?card( not found| missing)?\b"]):
        return 'functional_errors'
    if _regex_any(t, [r"\b(sell amount|sell|coins?|amount|balance|incent|incentive)\b"]):
        return 'data_integrity_issues'
    if _regex_any(t, [r"\b(quality|bad quality|quality issue|damaged|damage|spoil(ed)?|waste|dented)\b"]):
        return 'product_quality_issues'

    # Explicit crash/error indicators
    if _match_any(t, ['error', 'exception', 'fatal', 'stack trace']):
        return 'functional_errors'

    # Auth indicators on screen (expanded locales)
    if _match_any(t, ['sign in', 'login', 'password', 'otp', 'pin', 'mpin']) or _regex_any(t, [
        r"\b(otp nahi|otp नहीं|otp வரவில்லை|पासवर्ड|लॉगिन|साइन इन)\b"
    ]):
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

    # Payment/integration words (expanded)
    if _match_any(t, ['payment', 'transaction', 'gateway', 'upi', 'printer', 'bluetooth']) or _regex_any(t, [
        r"\b(bhim|phonepe|gpay|paytm|tez)\b",
        r"\b(upi fail(ed)?|payment fail(ed)?|payment pending|gateway error)\b"
    ]):
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


def _compute_confidence(matched_keywords: int, structured_present: bool, strong_rule: bool, model_used: bool, final_category: str) -> float:
    # Base confidence
    conf = 0.3
    if strong_rule:
        conf = 0.7
    if matched_keywords:
        conf = max(conf, 0.7 + min(0.2, 0.05 * (matched_keywords - 1)))  # up to 0.9
    if structured_present and conf < 0.85:
        conf += 0.05
    if model_used and conf < 0.7:
        conf = 0.7
    # Clamp
    return float(max(0.0, min(0.99, conf)))


def categorize_record_with_meta(record: Dict, ocr_texts: Optional[List[str]] = None, filenames: Optional[List[str]] = None, model_pred: Optional[str] = None) -> Tuple[str, float, str]:
    """
    Determine the best category for a record using deterministic heuristics with rules.json.
    Priority order:
      1) Strong comment-based rules
      2) Strong OCR-based rules
      3) Strong filename-based rules
      4) Config keyword_map with priority tie-breaker
      5) Post-adjustment overrides
      6) Best-effort weak signals
      7) Strict unclear gate
    """
    # Prefer translated comment if present
    effective_comment_raw = record.get('comment_translated') or record.get('comment', '')
    comment = _norm(effective_comment_raw)
    strong_rule_applied = False
    reason = 'unknown'

    # 1) Comment
    c = categorize_from_comment(comment)
    if c:
        strong_rule_applied = True
        reason = 'strong_comment_regex'
        return c, _compute_confidence(0, False, True, False, c), reason

    # 2) OCR
    if ocr_texts:
        for t in ocr_texts:
            cat = categorize_from_ocr(t)
            if cat:
                strong_rule_applied = True
                reason = 'strong_ocr_regex'
                return cat, _compute_confidence(0, False, True, False, cat), reason

    # 3) Filename
    if filenames:
        for fn in filenames:
            cat = categorize_from_filename(fn)
            if cat:
                strong_rule_applied = True
                reason = 'filename_rule'
                return cat, _compute_confidence(0, False, True, False, cat), reason

    # 3.5) Keyword mapping from rules.json across combined comment + OCR
    combined_texts: List[str] = []
    if comment:
        combined_texts.append(comment)
    for t in (ocr_texts or []):
        if t:
            combined_texts.append(_norm(t))
    combined = ' \n '.join(combined_texts)
    matched_kws, matched_cats = _keyword_matches(combined)
    if matched_cats:
        resolved = _resolve_by_priority(matched_cats)
        reason = 'regex_map' if any(k.startswith('re:') for k in matched_kws) else 'keyword_map'
        return resolved or 'functional_errors', _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, resolved or 'functional_errors'), reason

    # 4) Post-adjustment
    signals = {
        'explicit_crash': _match_any(comment, ['crash', 'force close', 'stopped working']),
        'explicit_connectivity': _match_any(comment, ['unable to connect', 'network error', 'api failed', 'timeout']),
        'explicit_auth': _match_any(comment, ['login', 'sign in', 'password', 'otp'])
    }
    adjusted = post_adjustment(model_pred, signals)
    if adjusted:
        # If post_adjustment suggests a specific non-unclear category (e.g., due to explicit signals), accept it now.
        if adjusted != 'unclear_insufficient_info':
            reason = 'post_adjustment' if any(signals.values()) else 'model_pred'
            return adjusted, _compute_confidence(0, _structured_tokens_present(comment), strong_rule_applied, model_pred is not None, adjusted), reason
        # If adjusted is 'unclear_insufficient_info', do NOT return yet.
        # We'll apply the strict unclear gate later to avoid assigning unclear when usable content exists.

    # 4.5) Weak-signal, best-effort mapping before giving up
    # Combine available texts for lightweight heuristics
    combined_texts = []
    # Do NOT overwrite the previously computed 'comment' (which prefers translated text)
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
            cat = 'data_integrity_issues'
            reason = 'weak_signal_data_integrity'
            return cat, _compute_confidence(len(matched_kws), True, strong_rule_applied, False, cat), reason

        # Generic error/functionality hints (tightened)
        generic_error_tokens = ["error", "fail", "failed", "not working", "does not work", "unable", "stuck", "cannot", "can't"]
        generic_hits = [tok for tok in generic_error_tokens if tok in combined]
        has_structured = _structured_tokens_present(combined)
        if len(generic_hits) >= 2 or (len(generic_hits) >= 1 and has_structured):
            cat = 'functional_errors'
            reason = 'weak_signal_generic_strong'
            return cat, _compute_confidence(len(matched_kws), has_structured, strong_rule_applied, False, cat), reason
        # If only 1 weak generic hint and no structured signals, avoid over-routing
        if len(generic_hits) == 1 and not has_structured:
            # Prefer model prediction if present
            if model_pred and model_pred != 'unclear_insufficient_info':
                reason = 'model_pred_weak_generic'
                return model_pred, _compute_confidence(len(matched_kws), has_structured, strong_rule_applied, True, model_pred), reason
            # Or fallback to UI/UX if UI words present
            if _match_any(combined, ["button", "screen", "page", "icon", "text", "label", "alignment", "visible", "display"]):
                cat = 'ui_ux_issues'
                reason = 'weak_signal_uiux_from_generic'
                return cat, _compute_confidence(len(matched_kws), has_structured, strong_rule_applied, False, cat), reason

        # Connectivity weaker hints
        weak_connectivity = ["no internet", "network", "server", "timeout", "api", "internet nahi", "server down", "net problem"]
        has_weak_conn = _match_any(combined, weak_connectivity)
        if has_weak_conn:
            cat = 'connectivity_problems'
            reason = 'weak_signal_connectivity'
            return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # Auth weaker hints
        weak_auth = ["otp", "signin", "sign in", "login", "password", "pin", "mpin", "forgot password"]
        has_weak_auth = _match_any(combined, weak_auth)
        if has_weak_auth:
            cat = 'authentication_access'
            reason = 'weak_signal_auth'
            return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # Integration weaker hints
        weak_integration = ["printer", "bluetooth", "gateway", "upi", "payment", "transaction", "scan", "weighing scale", "barcode"]
        has_weak_integration = _match_any(combined, weak_integration)
        if has_weak_integration:
            cat = 'integration_failures'
            reason = 'weak_signal_integration'
            return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # UI/UX weaker hints: loosen to 1 token with guardrails (no conflicting weak auth/conn/integration and no generic functional hits)
        ui_tokens = ["button", "screen", "page", "icon", "font", "text", "label", "alignment", "visible", "display", "scroll", "cut off", "overlap"]
        ui_hits = [tok for tok in ui_tokens if tok in combined]
        if len(ui_hits) >= 1 and not (has_weak_auth or has_weak_conn or has_weak_integration) and len(generic_hits) == 0:
            cat = 'ui_ux_issues'
            reason = 'weak_signal_uiux_loose'
            return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # Performance weaker hints
        perf_tokens = ["slow", "lag", "loading", "hang", "hanging", "sluggish", "takes too long", "please wait", "processing"]
        if _match_any(combined, perf_tokens) and not _match_any(combined, ["success", "completed", "done"]):
            cat = 'performance_issues'
            reason = 'weak_signal_performance'
            return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # Fuzzy small-token heuristics
        if _fuzzy_contains(combined, 'coins'):
            cat = 'data_integrity_issues'
            reason = 'fuzzy_data_integrity'
            return cat, _compute_confidence(len(matched_kws) + 1, True, strong_rule_applied, False, cat), reason
        if _fuzzy_contains(combined, 'quality') or _fuzzy_contains(combined, 'damage'):
            cat = 'product_quality_issues'
            reason = 'fuzzy_quality'
            return cat, _compute_confidence(len(matched_kws) + 1, _structured_tokens_present(combined), strong_rule_applied, False, cat), reason

        # Filename-driven weak signals if text was inconclusive
        if filenames:
            fn_join = " \n ".join(_norm(fn) for fn in filenames if fn)
            if fn_join:
                if any(tok in fn_join for tok in ui_tokens):
                    cat = 'ui_ux_issues'
                    reason = 'weak_signal_from_filename_ui'
                    return cat, _compute_confidence(0, _structured_tokens_present(fn_join), strong_rule_applied, False, cat), reason
                if any(tok in fn_join for tok in ["printer", "bluetooth", "gateway", "upi", "payment", "transaction", "scan", "weighing scale", "barcode"]):
                    cat = 'integration_failures'
                    reason = 'weak_signal_from_filename_integration'
                    return cat, _compute_confidence(0, _structured_tokens_present(fn_join), strong_rule_applied, False, cat), reason
                if any(tok in fn_join for tok in ["no internet", "network", "server", "timeout", "api", "internet nahi", "server down", "net problem"]):
                    cat = 'connectivity_problems'
                    reason = 'weak_signal_from_filename_connectivity'
                    return cat, _compute_confidence(0, _structured_tokens_present(fn_join), strong_rule_applied, False, cat), reason

    # 4.8) If model has a prediction, prefer it (non-unclear only at this stage)
    if model_pred and model_pred != 'unclear_insufficient_info':
        reason = 'model_pred'
        return model_pred, _compute_confidence(len(matched_kws), _structured_tokens_present(comment), strong_rule_applied, True, model_pred), reason

    # 5) Final decision with strict unclear gate
    if allow_unclear_label(record, ocr_texts=ocr_texts, filenames=filenames):
        reason = 'unclear_gate'
        return 'unclear_insufficient_info', 0.3, reason

    # If we reach here, there is usable content but no strong/weak match.
    # Prefer model prediction if any; otherwise default to a generic, action-oriented class.
    if model_pred:
        reason = 'model_pred_fallback'
        return model_pred, _compute_confidence(len(matched_kws), _structured_tokens_present(comment), strong_rule_applied, True, model_pred), reason
    cat = 'functional_errors'
    reason = 'default_fallback'
    return cat, _compute_confidence(len(matched_kws), _structured_tokens_present(comment), strong_rule_applied, False, cat), reason


def categorize_record(record: Dict, ocr_texts: Optional[List[str]] = None, filenames: Optional[List[str]] = None, model_pred: Optional[str] = None) -> str:
    """Backward-compatible wrapper returning only category."""
    cat, _conf, _reason = categorize_record_with_meta(record, ocr_texts=ocr_texts, filenames=filenames, model_pred=model_pred)
    return cat


__all__ = [
    'categorize_record',
    'categorize_record_with_meta',
    'categorize_from_comment',
    'categorize_from_ocr',
    'categorize_from_filename',
    'post_adjustment',
    'allow_unclear_label'
]
