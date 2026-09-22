"""Конвейер анализа и маскирования ПД (раздел 5 SPEC).

analyze: структурная детекция + NER → фильтр по типам → подтверждение bare-спанов →
resolve_overlaps → (опц.) отбрасывание pin/cvv без карты → типы. mask_text —
analyze + apply_masks. NER-движок выбирается NER_ENGINE через importlib с откатом на fast.
"""
from __future__ import annotations

import importlib
import logging
import os

from app.detectors import Span, detect_structured, resolve_overlaps
from app.lexicon import ADDRESS_CONTEXT
from app.masking import apply_masks

log = logging.getLogger(__name__)

# Типы, требующие подтверждения контекстом (bare-спаны).
_BARE_DEPT = "dept_code"
_BARE_ADDR = "address"


def _select_ner() -> object:
    """Выбирает NER-движок по NER_ENGINE; при ошибке импорта — откат на fast."""
    engine = os.environ.get("NER_ENGINE", "fast")
    if engine == "natasha":
        try:
            return importlib.import_module("app.ner")
        except ImportError:
            log.warning("NER_ENGINE=natasha недоступен, откат на fast")
    return importlib.import_module("app.fast_ner")


def _confirm_bare(spans: list[Span], text: str) -> list[Span]:
    """Подтверждает bare-спаны: dept_code — есть паспорт; address — другой адрес или контекст."""
    types = {s.type for s in spans}
    has_passport = "passport" in types
    has_addr = any(s.type == _BARE_ADDR and not s.meta.get("bare") for s in spans)
    has_ctx = ADDRESS_CONTEXT.search(text) is not None
    result: list[Span] = []
    for s in spans:
        if s.meta.get("bare"):
            if s.type == _BARE_DEPT and not has_passport:
                continue
            if s.type == _BARE_ADDR and not (has_addr or has_ctx):
                continue
        result.append(s)
    return result


def _drop_contextual(spans: list[Span]) -> list[Span]:
    """При contextual=True без карты выбрасывает card_pin и cvv."""
    if any(s.type == "card" for s in spans):
        return spans
    return [s for s in spans if s.type not in ("card_pin", "cvv")]


def analyze(
    text: str,
    allowed_types: list[str] | None = None,
    *,
    contextual: bool = False,
) -> tuple[list[Span], list[str]]:
    """Находит спаны ПД и типы; порядок конвейера фиксирован (раздел 5 SPEC)."""
    ner = _select_ner()
    spans = detect_structured(text) + ner.detect_names_and_addresses(text)
    if allowed_types is not None:
        allowed = set(allowed_types)
        spans = [s for s in spans if s.type in allowed]
    spans = _confirm_bare(spans, text)
    if contextual:
        spans = _drop_contextual(spans)
    spans = resolve_overlaps(spans)
    spans.sort(key=lambda s: s.start)
    detected = sorted({s.type for s in spans})
    return spans, detected


def mask_text(
    text: str,
    allowed_types: list[str] | None = None,
    *,
    contextual: bool = False,
) -> tuple[str, list[str]]:
    """Маскирует ПД в тексте; возвращает (маскированный_текст, типы)."""
    spans, detected = analyze(text, allowed_types, contextual=contextual)
    return apply_masks(text, spans), detected