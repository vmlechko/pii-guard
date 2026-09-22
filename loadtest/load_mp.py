"""Многопроцессный нагрузочный тест — обходит GIL однопроцессного клиента.

Порождает P процессов, каждый крутит asyncio-цикл с C соединениями D секунд, шлёт пары
маска→демаск (как проверяющая система) и меряет латентность. Итог агрегируется.

Запуск:
  python loadtest/load_mp.py --url http://127.0.0.1:8100 --procs 6 --conc 16 --duration 15
"""
from __future__ import annotations

import argparse
import asyncio
import multiprocessing as mp
import time
import uuid

import httpx

SAMPLES = [
    "Клиент Иванов Иван Иванович, паспорт 4509 123456, тел +7 916 123-45-67",
    "карта 4276 3800 1234 5678, CVV 123, пин-код 4321, email a.ivanov@example.com",
    "ИНН 5051808187, индекс 101000, г. Москва, ул. Тверская, д. 5, кв. 12",
    "СНИЛС 112-233-445 95, водительское удостоверение 99 07 123456",
]


def run_proc(args) -> tuple[int, list[float], int]:
    url, conc, dur = args

    async def main() -> tuple[list[float], int]:
        lat: list[float] = []
        errs = 0
        limits = httpx.Limits(max_connections=conc, max_keepalive_connections=conc)
        async with httpx.AsyncClient(base_url=url, timeout=10, limits=limits) as c:
            stop = time.perf_counter() + dur

            async def worker() -> None:
                nonlocal errs
                i = 0
                while time.perf_counter() < stop:
                    pid = uuid.uuid4().hex
                    text = SAMPLES[i % len(SAMPLES)]
                    i += 1
                    t = time.perf_counter()
                    r1 = await c.post("/process", json={"payload": text, "payload_id": pid})
                    lat.append((time.perf_counter() - t) * 1000)
                    mask = r1.json()["result"]
                    t = time.perf_counter()
                    r2 = await c.post("/process", json={"payload": mask, "payload_id": pid})
                    lat.append((time.perf_counter() - t) * 1000)
                    if r2.json()["result"] != text:
                        errs += 1

            await asyncio.gather(*[worker() for _ in range(conc)])
        return lat, errs

    lat, errs = asyncio.run(main())
    return len(lat), lat, errs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8100")
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--conc", type=int, default=16)
    ap.add_argument("--duration", type=int, default=15)
    args = ap.parse_args()

    with mp.Pool(args.procs) as pool:
        t0 = time.perf_counter()
        results = pool.map(run_proc, [(args.url, args.conc, args.duration)] * args.procs)
        wall = time.perf_counter() - t0

    total = sum(r[0] for r in results)
    all_lat = sorted(x for r in results for x in r[1])
    errs = sum(r[2] for r in results)

    def pct(p: float) -> float:
        return all_lat[min(len(all_lat) - 1, int(len(all_lat) * p))] if all_lat else 0.0

    print(f"Процессов×соединений : {args.procs} × {args.conc} = {args.procs * args.conc}")
    print(f"Запросов всего       : {total}  (пар: {total // 2})")
    print(f"Время                : {wall:.1f} c")
    print(f"RPS                  : {total / args.duration:,.0f}")
    print(f"Ошибок               : {errs}")
    print(f"Латентность мс       : p50={pct(0.5):.1f}  p95={pct(0.95):.1f}  p99={pct(0.99):.1f}")


if __name__ == "__main__":
    main()
