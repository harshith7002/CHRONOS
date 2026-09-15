"""
CHRONOS Idempotency Engine
Ensures strict exactly-once execution semantics for all state-changing tool operations.
"""

from __future__ import annotations
import hashlib
import json
import threading
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field


class IdempotencyRecord(BaseModel):
    idempotency_key: str
    call_id: str
    snapshot_id: str
    tool_name: str
    arguments_hash: str
    created_at: float
    committed_at: Optional[float] = None
    status: str = "COMMITTED"
    result_payload: Optional[Any] = None


class IdempotencyRegistry:
    """
    Thread-safe deduplication and idempotency ledger.
    """

    def __init__(self):
        self._records: Dict[str, IdempotencyRecord] = {}
        self._call_id_to_key: Dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def generate_key(tool_name: str, snapshot_id: str, arguments: Dict[str, Any]) -> str:
        """Deterministically derive an idempotency key from tool, snapshot, and arguments."""
        sorted_args = json.dumps(arguments, sort_keys=True)
        raw_key = f"{tool_name}:{snapshot_id}:{sorted_args}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
        return f"idem_{tool_name}_{digest}"

    def register_or_get(
        self,
        idempotency_key: str,
        call_id: str,
        snapshot_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        created_at: float,
    ) -> Tuple[bool, Optional[IdempotencyRecord]]:
        """
        Check if key exists.
        Returns: (is_new, record)
        If is_new is False, this is a duplicate call that must return the cached result.
        """
        with self._lock:
            sorted_args = json.dumps(arguments, sort_keys=True)
            args_hash = hashlib.sha256(sorted_args.encode("utf-8")).hexdigest()

            if idempotency_key in self._records:
                existing = self._records[idempotency_key]
                return False, existing

            record = IdempotencyRecord(
                idempotency_key=idempotency_key,
                call_id=call_id,
                snapshot_id=snapshot_id,
                tool_name=tool_name,
                arguments_hash=args_hash,
                created_at=created_at,
                status="PREPARED",
            )
            self._records[idempotency_key] = record
            self._call_id_to_key[call_id] = idempotency_key
            return True, record

    def mark_committed(self, idempotency_key: str, committed_at: float, result_payload: Any) -> None:
        with self._lock:
            if idempotency_key in self._records:
                rec = self._records[idempotency_key]
                rec.committed_at = committed_at
                rec.status = "COMMITTED"
                rec.result_payload = result_payload

    def has_committed(self, idempotency_key: str) -> bool:
        with self._lock:
            if idempotency_key in self._records:
                return self._records[idempotency_key].status == "COMMITTED"
            return False

    def get_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._records.get(idempotency_key)

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._call_id_to_key.clear()
