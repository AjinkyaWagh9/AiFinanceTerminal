"""ModelRegistry — loads config/models.yaml and instantiates provider handles.

Provider classes are registered in providers/__init__.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .base import LLMProvider, ModelMetadata
from .providers import PROVIDERS


class ModelNotFound(Exception):
    pass


class ModelRegistry:
    def __init__(self, models_yaml: Path):
        self._meta: dict[str, ModelMetadata] = {}
        self._handles: dict[str, LLMProvider] = {}
        self._load(models_yaml)

    def _load(self, path: Path) -> None:
        data = yaml.safe_load(path.read_text())
        for entry in data.get("models", []):
            meta = ModelMetadata(
                name=entry["name"],
                provider=entry["provider"],
                api_id=entry["api_id"],
                context_window=entry["context_window"],
                cost_per_mtok_in=float(entry["cost_per_mtok_in"]),
                cost_per_mtok_out=float(entry["cost_per_mtok_out"]),
                capabilities=frozenset(entry.get("capabilities", [])),
                tags=frozenset(entry.get("tags", [])),
                api_key_env=entry.get("api_key_env"),
                base_url=entry.get("base_url"),
                base_url_env=entry.get("base_url_env"),
            )
            self._meta[meta.name] = meta

    def get(self, name: str) -> LLMProvider:
        if name not in self._meta:
            raise ModelNotFound(f"Model {name!r} not in registry")
        if name not in self._handles:
            meta = self._meta[name]
            provider_cls = PROVIDERS.get(meta.provider)
            if provider_cls is None:
                raise ModelNotFound(
                    f"Provider {meta.provider!r} not registered. "
                    f"Add it to src/finterminal/llm/providers/__init__.py"
                )
            self._handles[name] = provider_cls(meta)
        return self._handles[name]

    def by_capability(self, *caps: str) -> list[ModelMetadata]:
        return [m for m in self._meta.values() if set(caps).issubset(m.capabilities)]

    def by_tag(self, *tags: str) -> list[ModelMetadata]:
        return [m for m in self._meta.values() if set(tags).issubset(m.tags)]

    def all(self) -> list[ModelMetadata]:
        return list(self._meta.values())
