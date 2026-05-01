from __future__ import annotations

import hashlib
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class CacheItem:
    created_at: float
    value: Any


class DiskCache:
    """极简磁盘缓存（pickle）。

    说明：
    - 选择 pickle 是为了避免额外依赖（parquet/feather 往往需要 pyarrow）。
    - 适合缓存：财报/日线等低频数据。高频行情建议后续切到专门时序存储。
    """

    def __init__(self, cache_dir: Path, ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def make_key(self, namespace: str, payload: str) -> str:
        return f"{namespace}:{_sha256(payload)}"

    def _path_for_key(self, key: str) -> Path:
        safe = key.replace(":", "__")
        return self.cache_dir / f"{safe}.pkl"

    def get(self, key: str, ttl_seconds: Optional[int] = None) -> Optional[Any]:
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            item: CacheItem = pickle.loads(path.read_bytes())
        except Exception:
            return None

        effective_ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        if effective_ttl > 0 and (time.time() - item.created_at) > effective_ttl:
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return item.value

    def set(self, key: str, value: Any) -> None:
        path = self._path_for_key(key)
        tmp = path.with_suffix(".tmp")
        item = CacheItem(created_at=time.time(), value=value)
        tmp.write_bytes(pickle.dumps(item))
        tmp.replace(path)
