"""Маскирование значений ПД (раздел 5 SPEC).

mask_value — режим full (по умолчанию) или partial через переменную окружения
MASK_MODE. replace_spans — единственный цикл сборки строки; apply_masks и
tokenize используют его.
"""
from __future__ import annotations

import os
import re
from typing import Callable

from app.detectors import Span

# Режим маскирования: full — каждый буквенно-цифровой символ в «*»,
# partial — форматные маски, построенные из самого значения.
MASK_MODE = os.environ.get("MASK_MODE", "full")

# Буквенно-цифровые символы (подчёркивание — не буква), заменяются на «*».
_ALNUM = re.compile(r"[^\W_]")


def mask_all(text: str) -> str:
    """Заменяет каждый буквенно-цифровой символ на «*», разделители сохраняет."""
    return _ALNUM.sub("*", text)


def _mask_fio(text: str) -> str:
    """Инициалы через точку: «Иванов Иван» → «И. И.»."""
    words = [w for w in text.split() if w]
    return " ".join(f"{w[0]}." for w in words)


def _reveal_digits(text: str, head: int, tail: int) -> str:
    """Открывает head первых и tail последних цифр, остальные — «*» с разделителями."""
    digits = re.findall(r"\d", text)
    if len(digits) < head + tail:
        return mask_all(text)
    out: list[str] = []
    di = 0
    for ch in text:
        if ch.isdigit():
            if di < head or di >= len(digits) - tail:
                out.append(ch)
            else:
                out.append("*")
            di += 1
        else:
            out.append(ch)
    return "".join(out)


def _mask_passport(text: str) -> str:
    """Серия (≤4 цифр) — открыты первые 2; номер — последние 2."""
    if len(re.findall(r"\d", text)) <= 4:
        return _reveal_digits(text, 2, 0)
    return _reveal_digits(text, 0, 2)


def _mask_email(text: str) -> str:
    """Первая буква + «***» + «@домен»."""
    at = text.find("@")
    if at <= 0:
        return mask_all(text)
    return text[0] + "***" + text[at:]


def _mask_card(text: str) -> str:
    """Открыты последние 4 цифры, остальные цифры — «*» с разделителями."""
    return _reveal_digits(text, 0, 4)


# Таблица «тип → функция» для режима partial; остальные типы — mask_all.
_PARTIAL_MASKS: dict[str, Callable[[str], str]] = {
    "fio": _mask_fio,
    "passport": _mask_passport,
    "email": _mask_email,
    "card": _mask_card,
}


def mask_value(text: str, pii_type: str) -> str:
    """Маскирует значение ПД в режиме full или partial."""
    if MASK_MODE == "partial":
        return _PARTIAL_MASKS.get(pii_type, mask_all)(text)
    return mask_all(text)


def replace_spans(text: str, spans: list[Span], fn: Callable[[str, Span], str]) -> str:
    """Единственный цикл сборки строки: применяет fn к каждому спану."""
    if not spans:
        return text
    parts: list[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda s: s.start):
        parts.append(text[cursor : span.start])
        parts.append(fn(text[span.start : span.end], span))
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts)


def apply_masks(text: str, spans: list[Span]) -> str:
    """Заменяет все спаны масками по их типу."""
    return replace_spans(text, spans, lambda value, span: mask_value(value, span.type))