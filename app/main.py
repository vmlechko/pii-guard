"""FastAPI-приложение модуля безопасности ПД.

POST /process — маскирование/демаскирование по контракту раздела 1 SPEC.
GET /health — проверка живости. GET /metrics — метрики Prometheus.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from app.config import Config, SystemPolicy, load_config
from app.engine import mask_text
from app.metrics import CONTENT_TYPE, observe_request, observe_tokens, render
from app.store import Store, build_store

log = logging.getLogger(__name__)

app = FastAPI(title="Модуль безопасности ПД")

# Демо-прокси к LLM подключается опционально: отсутствие httpx не ломает сервис.
try:
    from app.llm_proxy import router as llm_router

    app.include_router(llm_router)
except ImportError:
    log.warning("llm_proxy недоступен, POST /demo/llm отключён")

# Конфигурация и стор загружаются один раз при старте приложения.
_config: Config = load_config(os.environ.get("PII_CONFIG", "config/systems.yaml"))
_store: Store = build_store(
    os.environ.get("REDIS_URL"),
    ttl_seconds=int(os.environ.get("PII_TTL", "3600")),
)


class ProcessRequest(BaseModel):
    """Тело запроса /process: текст и идентификатор полезной нагрузки."""

    payload: str
    payload_id: str


def _resolve_policy(x_system_id: str | None) -> SystemPolicy:
    """Выбирает политику по заголовку или системе по умолчанию; иначе 403."""
    system_id = x_system_id or _config.default_system
    policy = _config.get(system_id)
    if policy is None or not policy.enabled:
        raise HTTPException(status_code=403, detail="Система недоступна")
    return policy


def _load_record(payload_id: str):
    """Достаёт запись из стора; при ошибке стора логирует и возвращает None."""
    try:
        return _store.get(payload_id)
    except (ConnectionError, TimeoutError, OSError):
        log.warning("Ошибка чтения стора для payload_id=%s", payload_id)
        return None


def _mask_and_store(payload_id: str, payload: str, policy: SystemPolicy) -> str:
    """Маскирует текст и сохраняет пару (оригинал, маска); возвращает маску."""
    masked, types = mask_text(
        payload,
        policy.allowed_types,
        contextual=policy.contextual_masking,
    )
    log.info("Маскирование: типы=%s", {t: types.count(t) for t in set(types)})
    try:
        _store.put(payload_id, payload, masked)
    except (ConnectionError, TimeoutError, OSError):
        log.warning("Ошибка записи в стор для payload_id=%s", payload_id)
    return masked


def _handle(payload: str, payload_id: str, policy: SystemPolicy) -> tuple[str, str]:
    """Определяет направление и возвращает (результат, direction) по контракту раздела 1."""
    record = _load_record(payload_id)
    if record is None:
        return _mask_and_store(payload_id, payload, policy), "mask"
    if payload == record.original:
        return record.masked, "mask"  # идемпотентный ретрай — это маскирование
    if policy.demasking:
        return record.original, "demask"
    return record.masked, "demask"


@app.post("/process")
def process(
    request: ProcessRequest,
    x_system_id: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Обрабатывает запрос: маскирование или демаскирование."""
    policy = _resolve_policy(x_system_id)
    start = time.perf_counter()
    result, direction = _handle(request.payload, request.payload_id, policy)
    observe_request(direction, time.perf_counter() - start)
    observe_tokens(request.payload)
    return {"result": result}


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости сервиса."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    """Метрики Prometheus."""
    return Response(content=render(), media_type=CONTENT_TYPE)