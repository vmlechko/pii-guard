"""Производительность горячего пути: короткие запросы и тексты в ~100k токенов.

Организаторы ориентируют на ~1 с латентности сервиса; нагрузочная проверка идёт
на текстах разного размера, до ~100k токенов. Тесты страхуют от регрессий вида
O(n²) в разрешении пересечений или «взрывных» регулярных выражений.
"""
from __future__ import annotations

import time

from app.engine import mask_text

_FILLER = (
    "Согласно условиям договора обслуживания стороны обязуются выполнять взаимные "
    "обязательства в установленные сроки и порядке. "
)
_PII = "Клиент Иванов Иван Иванович, паспорт 4509 123456, тел +7 916 123-45-67, г. Москва, ул. Тверская, д. 7. "
SHORT = "Клиент Иванов Иван Иванович, паспорт 4509 123456, карта 4276 3800 1234 5678, тел +7 916 123-45-67"


def _elapsed_ms(text: str, repeats: int = 1) -> float:
    t0 = time.perf_counter()
    for _ in range(repeats):
        mask_text(text)
    return (time.perf_counter() - t0) * 1000 / repeats


def test_short_request_under_2ms() -> None:
    assert _elapsed_ms(SHORT, repeats=200) < 2.0


def test_100k_tokens_under_2s() -> None:
    big = "".join((_FILLER * 4 + (_PII if i % 2 == 0 else _FILLER)) for i in range(1100))
    assert len(big.split()) > 75_000
    assert _elapsed_ms(big) < 2000


def test_dense_pii_text_under_3s() -> None:
    # Худший случай: ~35 000 спанов ПД в одном тексте.
    dense = _PII * 5000
    assert _elapsed_ms(dense) < 3000
