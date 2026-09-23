"""Локальный нагрузочный тест /process.

Эмулирует поведение проверяющей системы: на каждый элемент — пара запросов с одним
payload_id (маскирование, затем демаскирование). Меряет достигнутый RPS и перцентили
латентности, считает ошибки.

Запуск:
  python loadtest/load.py --url http://127.0.0.1:8100 --concurrency 50 --duration 15
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid

import httpx

PROCESS_PATH = "/process"

SAMPLES = [
    "Клиент Иванов Иван Иванович, паспорт 4509 123456, тел +7 916 123-45-67",
    "карта 4276 3800 1234 5678, CVV 123, пин-код 4321, email a.ivanov@example.com",
    "ИНН 5051808187, индекс 101000, г. Москва, ул. Тверская, д. 5, кв. 12",
    "СНИЛС 112-233-445 95, водительское удостоверение 99 07 123456",
    "Петров Пётр Сергеевич родился 05.03.1990, дата выдачи паспорта 12.04.2015",
    "поэт Александр Пушкин упомянут рядом с клиентом Сидоровой Анной Петровной",
]


async def worker(client: httpx.AsyncClient, stop_at: float, lat: list, errs: list) -> None:
    while time.perf_counter() < stop_at:
        pid = uuid.uuid4().hex
        text = SAMPLES[int(time.perf_counter() * 1000) % len(SAMPLES)]
        try:
            t0 = time.perf_counter()
            r1 = await client.post(PROCESS_PATH, json={"payload": text, "payload_id": pid})
            lat.append(time.perf_counter() - t0)
            mask = r1.json()["result"]
            t0 = time.perf_counter()
            r2 = await client.post(PROCESS_PATH, json={"payload": mask, "payload_id": pid})
            lat.append(time.perf_counter() - t0)
            if r1.status_code != 200 or r2.status_code != 200 or r2.json()["result"] != text:
                errs.append(1)
        except Exception:  # noqa: BLE001
            errs.append(1)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100")
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--duration", type=int, default=15)
    args = ap.parse_args()

    lat: list[float] = []
    errs: list[int] = []
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.url, timeout=10, limits=limits) as client:
        await client.post(PROCESS_PATH, json={"payload": "warmup", "payload_id": "w"})  # прогрев
        stop_at = time.perf_counter() + args.duration
        t0 = time.perf_counter()
        await asyncio.gather(*[worker(client, stop_at, lat, errs) for _ in range(args.concurrency)])
        wall = time.perf_counter() - t0

    n = len(lat)
    ms = sorted(x * 1000 for x in lat)

    def pct(p: float) -> float:
        return ms[min(len(ms) - 1, int(len(ms) * p))] if ms else 0.0

    print(f"Запросов всего : {n}  (пар маска+демаск: {n // 2})")
    print(f"Время          : {wall:.1f} c")
    print(f"RPS            : {n / wall:,.0f}")
    print(f"Ошибок         : {len(errs)}")
    print(f"Латентность мс : p50={pct(0.5):.1f}  p95={pct(0.95):.1f}  p99={pct(0.99):.1f}  max={ms[-1] if ms else 0:.1f}")
    print(f"Средняя мс     : {statistics.mean(ms):.2f}" if ms else "n/a")


if __name__ == "__main__":
    asyncio.run(main())
