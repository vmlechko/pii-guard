"""Демо-прокси к LLM: токенизация → (опц.) вызов LLM → детокенизация (раздел 2 SPEC).

В LLM уходит только токенизированный текст; оригиналы ПД остаются в mapping внутри
сервиса. Без ALFAGEN_API_KEY честно возвращает токенизированный текст без вызова.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.tokenizer import detokenize, tokenize

log = logging.getLogger(__name__)

router = APIRouter()


class DemoRequest(BaseModel):
    """Тело запроса /demo/llm: исходный текст для токенизации и вызова LLM."""

    prompt: str


def _call_llm(tokenized: str) -> str:
    """Вызывает chat/completions с токенизированным текстом; возвращает ответ модели."""
    url = os.environ["ALFAGEN_BASE_URL"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {os.environ['ALFAGEN_API_KEY']}"}
    payload = {
        "model": os.environ["ALFAGEN_MODEL"],
        "messages": [{"role": "user", "content": tokenized}],
    }
    with httpx.Client(timeout=30.0, verify=True) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@router.post("/demo/llm")
def demo_llm(request: DemoRequest) -> dict:
    """Токенизирует prompt, вызывает LLM (если задан ключ) и детокенизирует ответ."""
    tokenized, mapping, detected = tokenize(request.prompt)
    called_llm = False
    if os.environ.get("ALFAGEN_API_KEY"):
        try:
            llm_out = _call_llm(tokenized)
            called_llm = True
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            log.warning("Ошибка вызова LLM: %s", exc)
            return {
                "result": tokenized,
                "tokenized_sent": tokenized,
                "detected": detected,
                "called_llm": False,
                "error": "LLM недоступен",
            }
    else:
        llm_out = tokenized
    result = detokenize(llm_out, mapping)
    return {
        "result": result,
        "tokenized_sent": tokenized,
        "detected": detected,
        "called_llm": called_llm,
    }