"""Токенизация ПД: замена значений на плейсхолдеры и обратно (раздел 2 SPEC).

tokenize — анализирует текст, заменяет каждое значение ПД на плейсхолдер
[<ТИП>_<N>] и ведёт mapping плейсхолдер → оригинал. detokenize — восстанавливает
оригиналы, длинные плейсхолдеры первыми, чтобы [FIO_1] не портил [FIO_10].
"""
from __future__ import annotations

from app.engine import analyze
from app.masking import replace_spans


def tokenize(text: str) -> tuple[str, dict[str, str], list[str]]:
    """Заменяет значения ПД на плейсхолдеры; возвращает (текст, mapping, detected)."""
    spans, detected = analyze(text)
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}

    def _placeholder(value: str, span) -> str:
        counters[span.type] = counters.get(span.type, 0) + 1
        placeholder = f"[{span.type.upper()}_{counters[span.type]}]"
        mapping[placeholder] = value
        return placeholder

    tokenized = replace_spans(text, spans, _placeholder)
    return tokenized, mapping, detected


def detokenize(text: str, mapping: dict[str, str]) -> str:
    """Восстанавливает оригиналы ПД из плейсхолдеров, длинные первыми."""
    for placeholder in sorted(mapping, key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text