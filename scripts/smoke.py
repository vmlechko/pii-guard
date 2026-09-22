"""Smoke-проверка пайплайна: маскирование → демаскирование по контракту /process.

Проверяющий может убедиться, что развёрнутый сервис работает, одной командой:
    python scripts/smoke.py http://localhost:8000

Скрипт делает пару запросов (маска, затем демаска с тем же payload_id), печатает
результаты и завершается с кодом 0 при успехе (демаска совпала с оригиналом) или 1 при сбое.
"""
from __future__ import annotations

import sys
import uuid

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SAMPLE = "Клиент Иванов Иван Иванович, паспорт 4509 123456, карта 4276 3800 1234 5678, тел +7 916 123-45-67"


def main() -> int:
    pid = uuid.uuid4().hex
    with httpx.Client(base_url=URL, timeout=10) as c:
        masked = c.post("/process", json={"payload": SAMPLE, "payload_id": pid}).json()["result"]
        restored = c.post("/process", json={"payload": masked, "payload_id": pid}).json()["result"]

    print("Оригинал :", SAMPLE)
    print("Маска    :", masked)
    print("Демаска  :", restored)
    ok = masked != SAMPLE and restored == SAMPLE
    print("\nИТОГ:", "OK — пайплайн воспроизводится" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
