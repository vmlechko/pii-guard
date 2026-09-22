"""Конфигурация систем-потребителей из config/systems.yaml.

Политика системы определяет, какие типы ПД маскировать, доступна ли система и
разрешено ли демаскирование. При отсутствии файла конфигурации используется
дефолт: все типы, демаскирование включено.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.pii_types import ALL_TYPES


@dataclass
class SystemPolicy:
    """Политика одной системы-потребителя."""

    name: str
    enabled: bool = True
    allowed_types: list[str] = field(default_factory=lambda: list(ALL_TYPES))
    demasking: bool = True
    contextual_masking: bool = False


@dataclass
class Config:
    """Набор политик систем и система по умолчанию."""

    systems: dict[str, SystemPolicy]
    default_system: str = "default"

    def get(self, system_id: str) -> SystemPolicy | None:
        """Возвращает политику системы или None, если её нет."""
        return self.systems.get(system_id)


def _default_config() -> Config:
    """Конфигурация по умолчанию: одна включённая система со всеми типами."""
    return Config(systems={"default": SystemPolicy(name="Базовая система")})


def load_config(path: str | Path) -> Config:
    """Читает YAML-конфигурацию систем; при отсутствии файла — дефолт."""
    config_path = Path(path)
    if not config_path.is_file():
        return _default_config()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    systems = {
        system_id: SystemPolicy(
            name=spec.get("name", system_id),
            enabled=spec.get("enabled", True),
            allowed_types=spec.get("allowed_types", list(ALL_TYPES)),
            demasking=spec.get("demasking", True),
            contextual_masking=spec.get("contextual_masking", False),
        )
        for system_id, spec in raw.get("systems", {}).items()
    }
    return Config(systems=systems, default_system=raw.get("default_system", "default"))