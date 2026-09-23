"""Стор для хранения пар (оригинал, маска) по payload_id.

Два варианта: InMemoryStore (dict + Lock, TTL, чистка при переполнении)
и RedisStore (HSET + EXPIRE). build_store выбирает реализацию по redis_url.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Record:
    """Пара «оригинал — маска» для одного payload_id."""

    original: str
    masked: str


class Store(Protocol):
    """Контракт стора: положить и достать запись по payload_id."""

    def get(self, payload_id: str) -> Record | None:
        """Вернуть запись или None, если её нет или она протухла."""

    def put(self, payload_id: str, original: str, masked: str) -> None:
        """Сохранить запись с текущим временем создания."""


class InMemoryStore:
    """Хранилище в памяти: dict + Lock, TTL и чистка при переполнении."""

    def __init__(self, ttl_seconds: int, max_records: int = 500_000) -> None:
        self._ttl = ttl_seconds
        self._max = max_records
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, Record]] = {}

    def get(self, payload_id: str) -> Record | None:
        """Вернуть запись, если она есть и не протухла."""
        with self._lock:
            entry = self._data.get(payload_id)
            if entry is None:
                return None
            created, record = entry
            if time.monotonic() - created > self._ttl:
                del self._data[payload_id]
                return None
            return record

    def put(self, payload_id: str, original: str, masked: str) -> None:
        """Сохранить запись; при переполнении почистить протухшие или старейшие."""
        with self._lock:
            self._data[payload_id] = (time.monotonic(), Record(original, masked))
            if len(self._data) <= self._max:
                return
            self._evict_expired()
            if len(self._data) > self._max:
                self._evict_oldest()

    def _evict_expired(self) -> None:
        """Удалить все протухшие записи."""
        now = time.monotonic()
        expired = [
            pid for pid, (created, _) in self._data.items()
            if now - created > self._ttl
        ]
        for pid in expired:
            del self._data[pid]

    def _evict_oldest(self) -> None:
        """Удалить старейшие 10 % записей."""
        count = max(1, len(self._data) // 10)
        oldest = sorted(self._data, key=lambda pid: self._data[pid][0])[:count]
        for pid in oldest:
            del self._data[pid]


class RedisStore:
    """Хранилище в Redis: HSET o/m + EXPIRE, ключи с префиксом pii:."""

    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        import redis  # импорт внутри класса, чтобы не тянуть зависимость на уровне модуля

        self._ttl = ttl_seconds
        self._client = redis.from_url(redis_url)

    def get(self, payload_id: str) -> Record | None:
        """Вернуть запись из Redis или None, если её нет."""
        data = self._client.hgetall(self._key(payload_id))
        if not data:
            return None
        return Record(data[b"o"].decode(), data[b"m"].decode())

    def put(self, payload_id: str, original: str, masked: str) -> None:
        """Сохранить запись в Redis с TTL."""
        key = self._key(payload_id)
        self._client.hset(key, mapping={"o": original, "m": masked})
        self._client.expire(key, self._ttl)

    @staticmethod
    def _key(payload_id: str) -> str:
        """Ключ Redis с префиксом."""
        return f"pii:{payload_id}"


def build_store(redis_url: str | None, ttl_seconds: int) -> Store:
    """Выбрать реализацию стора: Redis при заданном URL, иначе в памяти."""
    if redis_url:
        return RedisStore(redis_url, ttl_seconds)
    return InMemoryStore(ttl_seconds)