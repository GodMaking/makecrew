"""Small durable-checkpoint and bounded-retry contracts for host adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import time
from typing import Any


@dataclass(frozen=True)
class RetryPolicy:
    """Describe when a failed host operation may resume from its last checkpoint."""

    max_attempts: int = 3
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts 必须大于 0")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds 不能为负数")

    def decision(self, *, attempt: int, retryable: bool) -> dict[str, Any]:
        if attempt < 1:
            raise ValueError("attempt 必须从 1 开始")
        should_retry = retryable and attempt < self.max_attempts
        return {
            "action": "retry" if should_retry else "stop",
            "attempt": attempt,
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds if should_retry else 0,
            "resume_from": "last_checkpoint" if should_retry else "none",
            "reason": "retryable_failure" if should_retry else "retry_budget_exhausted_or_non_retryable",
        }


class JsonCheckpointStore:
    """Persist compact node state with idempotency-key deduplication."""

    VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"检查点文件无效：{self.path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"检查点文件结构无效：{self.path}")
        records = payload.get("records")
        if payload.get("version") != self.VERSION or not isinstance(records, list):
            raise ValueError(f"不支持的检查点版本：{payload.get('version')}")
        if any(not isinstance(item, dict) for item in records):
            raise ValueError(f"检查点记录结构无效：{self.path}")
        self._records = [dict(item) for item in records]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION, "records": self._records}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def save(
        self,
        task_id: str,
        node_id: str,
        state: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        task_id, node_id, idempotency_key = task_id.strip(), node_id.strip(), idempotency_key.strip()
        if not task_id or not node_id or not idempotency_key:
            raise ValueError("task_id、node_id 和 idempotency_key 不能为空")
        existing = next((item for item in self._records if item["idempotency_key"] == idempotency_key), None)
        if existing is not None:
            return dict(existing, state=dict(existing["state"]))
        record = {
            "checkpoint_id": f"CP-{len(self._records) + 1:06d}",
            "task_id": task_id,
            "node_id": node_id,
            "state": dict(state),
            "idempotency_key": idempotency_key,
            "sequence": len(self._records) + 1,
            "saved_at": time(),
        }
        self._records.append(record)
        self._save()
        return dict(record, state=dict(record["state"]))

    def load_latest(self, task_id: str) -> dict[str, Any] | None:
        matches = [item for item in self._records if item.get("task_id") == task_id.strip()]
        if not matches:
            return None
        latest = max(matches, key=lambda item: int(item.get("sequence", 0)))
        return dict(latest, state=dict(latest.get("state", {})))

    def audit(self) -> dict[str, Any]:
        return {
            "index": str(self.path),
            "version": self.VERSION,
            "records": len(self._records),
            "tasks": sorted({str(item.get("task_id", "")) for item in self._records}),
        }
