"""Метрики Prometheus для модуля безопасности ПД.

Собираем латентность обработки запроса, счётчик запросов по направлению
(mask/demask) и число обработанных токенов. Никогда не содержит текст ПД.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Гистограмма латентности обработки запроса в секундах.
pii_request_latency_seconds = Histogram(
    "pii_request_latency_seconds",
    "Время обработки запроса /process в секундах",
)

# Счётчик запросов с меткой направления (mask | demask).
pii_requests_total = Counter(
    "pii_requests_total",
    "Число обработанных запросов /process по направлению",
    ["direction"],
)

# Счётчик обработанных токенов.
pii_tokens_total = Counter(
    "pii_tokens_total",
    "Число обработанных токенов",
)

CONTENT_TYPE = CONTENT_TYPE_LATEST


def observe_request(direction: str, seconds: float) -> None:
    """Фиксирует латентность и счётчик запроса по направлению."""
    pii_request_latency_seconds.observe(seconds)
    pii_requests_total.labels(direction=direction).inc()


def observe_tokens(text: str) -> None:
    """Учитывает число токенов в тексте (число слов)."""
    pii_tokens_total.inc(len(text.split()))


def render() -> bytes:
    """Возвращает метрики в формате Prometheus."""
    return generate_latest()