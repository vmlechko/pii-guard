"""Опциональный нейросетевой NER на Natasha (NewsNERTagger): тот же интерфейс, что у fast_ner.

Импорт natasha на уровне модуля — если библиотека не установлена, ImportError
пробрасывается, и движок в engine._select_ner ловит его и откатывается на fast.
Синглтоны: сегментатор и нейро-теггер (загрузка модели дорогая).
"""
from __future__ import annotations

import re

from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter

from app.detectors import Span
from app.fast_ner import detect_addresses as _fast_addresses
from app.lexicon import FAMOUS_SURNAMES, STOP_TITLE_WORDS

_segmenter = Segmenter()
_ner_tagger = NewsNERTagger(NewsEmbedding())

_FAMOUS_RE = re.compile(r"\b(?:" + "|".join(sorted(FAMOUS_SURNAMES)) + r")\b")
_WORD_RE = re.compile(r"[А-ЯЁ][А-ЯЁа-яё]+")


def _strip_titles(text: str, start: int, end: int) -> int:
    """Отрезает обращения из STOP_TITLE_WORDS в начале спана."""
    while start < end:
        m = _WORD_RE.match(text, start, end)
        if m is None or m.group(0).lower() not in STOP_TITLE_WORDS:
            break
        start = m.end()
        while start < end and text[start].isspace():
            start += 1
    return start


def detect_names_and_addresses(text: str) -> list[Span]:
    """ФИО (PER) и адреса (LOC) через нейро-теггер; ORG игнорируется."""
    doc = Doc(text)
    doc.segment(_segmenter)
    doc.tag_ner(_ner_tagger)
    spans: list[Span] = []
    for s in doc.spans:
        if s.type == "PER":
            start = _strip_titles(text, s.start, s.stop)
            if start >= s.stop:
                continue
            if _FAMOUS_RE.search(text[start:s.stop].lower()) is not None:
                continue
            spans.append(Span(start, s.stop, "fio", 80))
        elif s.type == "LOC":
            spans.append(Span(s.start, s.stop, "address", 60))
    spans += _fast_addresses(text)
    return spans


def detect_names(text: str) -> list[Span]:
    """Только ФИО."""
    return [s for s in detect_names_and_addresses(text) if s.type == "fio"]


def detect_addresses(text: str) -> list[Span]:
    """Только адреса."""
    return [s for s in detect_names_and_addresses(text) if s.type == "address"]