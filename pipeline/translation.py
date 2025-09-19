#!/usr/bin/env python3
"""
translation.py

Utilities for lightweight language detection and translation to English for
bug report comments. We avoid heavy dependencies by using langdetect and
deep-translator (GoogleTranslator backend).

API:
    detect_and_translate(text: str) -> tuple[str|None, str|None]
        Returns (translated_text, detected_lang). If text is empty or already
        English, translated_text may be None.
"""
from __future__ import annotations

from typing import Optional, Tuple

try:
    from langdetect import detect  # type: ignore
except Exception:  # pragma: no cover
    detect = None  # Fallback when package not available

try:
    from deep_translator import GoogleTranslator  # type: ignore
except Exception:  # pragma: no cover
    GoogleTranslator = None  # Fallback when package not available


def _safe_detect(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    if detect is None:
        return None
    try:
        lang = detect(text)
        # Normalize common codes
        if lang:
            return lang.lower()
        return None
    except Exception:
        return None


def _safe_translate(text: str, src: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return None
    if GoogleTranslator is None:
        return None
    try:
        # If source is unknown, let the translator auto-detect
        translator = GoogleTranslator(source=src or 'auto', target='en')
        out = translator.translate(text)
        if isinstance(out, str) and out.strip():
            return out.strip()
        return None
    except Exception:
        return None


def detect_and_translate(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect language and translate to English when not already English.
    Returns (translated_text, detected_lang).
    - translated_text: None if translation not needed or failed.
    - detected_lang: BCP-47-ish 2-letter code when possible (e.g., 'en', 'ta').
    """
    input_text = (text or '').strip()
    if not input_text:
        return None, None

    lang = _safe_detect(input_text)
    if lang in (None, 'en'):
        return None, lang or 'en'

    translated = _safe_translate(input_text, src=lang)
    return translated, lang
