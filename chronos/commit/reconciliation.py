"""
CHRONOS External Action Reconciliation Engine
Handles in-flight timeouts, network disconnects, and post-interruption state reconciliation for irreversible writes.
"""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from chronos.commit.idempotency import IdempotencyRegistry
from chronos.commit.commit_controller import PrepareToken, CommitController


class ReconciliationResult(BaseModel):
    token_id: str
    idempotency_key: str
    action_committed: bool
    reconciled_status: str
    retry_required: bool
    reconciliation_details: Dict[str, Any] = Field(default_factory=dict)


class ActionReconciler:
    """
    Reconciles external state for in-flight state-changing operations before attempting safe retry.
    """

    def __init__(self, commit_controller: CommitController, idempotency: IdempotencyRegistry):
        self.commit_controller = commit_controller
        self.idempotency = idempotency

    def reconcile_irreversible_write(
        self,
        token_id: str,
        external_query_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> ReconciliationResult:
        """
        Policy:
        Timeout / Interruption in flight
             ↓
        Query External Status
             ↓
        Already Committed?
             ├── YES ➔ Record success in Idempotency Ledger (do NOT re-execute)
             └── NO  ➔ Safe retry with SAME idempotency key
        """
        token = self.commit_controller.get_token(token_id)
        if not token:
            raise ValueError(f"Token '{token_id}' not found for reconciliation")

        # 1. Query external system if handler provided
        external_status = None
        if external_query_fn:
            try:
                external_status = external_query_fn(token.idempotency_key)
            except Exception as ex:
                external_status = {"error": str(ex), "committed": False}

        already_committed = self.idempotency.has_committed(token.idempotency_key) or (
            external_status and external_status.get("committed", False)
        )

        if already_committed:
            # Sync idempotency ledger
            if not self.idempotency.has_committed(token.idempotency_key):
                self.idempotency.mark_committed(
                    token.idempotency_key,
                    self.commit_controller.clock.now(),
                    external_status or {"reconciled": True},
                )
            return ReconciliationResult(
                token_id=token_id,
                idempotency_key=token.idempotency_key,
                action_committed=True,
                reconciled_status="COMMITTED_EXTERNALLY",
                retry_required=False,
                reconciliation_details=external_status or {},
            )

        # Not committed yet: safe to retry with SAME idempotency key
        return ReconciliationResult(
            token_id=token_id,
            idempotency_key=token.idempotency_key,
            action_committed=False,
            reconciled_status="SAFE_FOR_IDEMPOTENT_RETRY",
            retry_required=True,
            reconciliation_details=external_status or {},
        )
