# CHRONOS: Temporal Control Plane for Interruptible Real-Time AI Agents

CHRONOS maintains strict agent state consistency during asynchronous tool executions, streaming interruptions, intent version transitions, and late-arriving stale results.

## Core Architectural Invariants

> **"Never blindly stop and restart. Version the intent, selectively invalidate obsolete work, preserve reusable work, reject stale results, and commit irreversible actions only after explicit confirmation."**

---

## Subsystems

1. **Protocol Layer (`chronos.protocol`)**:
   - Event definitions (`USER_INPUT`, `INTENT_UPDATE`, `INTERRUPTION`, `SNAPSHOT_CREATED`, `TOOL_DISPATCHED`, `TOOL_COMPLETED`, `TOOL_CANCELLED`, `TOOL_FAILED`, `STALE_RESULT_REJECTED`, `CONFIRMATION_REQUESTED`, `CONFIRMATION_RECEIVED`, `COMMIT`, `FINAL_RESPONSE`).
   - Execution Classes: `READ_ONLY`, `REVERSIBLE_WRITE`, `IRREVERSIBLE_WRITE`.

2. **Deterministic Virtual Clock (`chronos.clock`)**:
   - Independent virtual time abstraction for repeatable simulation, microsecond stepping, and wall-clock sync.

3. **Temporal State Manager (`chronos.state`)**:
   - Event-sourced architecture with immutable state snapshots ($v_1 \rightarrow v_2 \rightarrow v_3 \dots$).
   - Multi-branch tree lifecycle (`ACTIVE`, `SUPERSEDED`, `COMPLETED`, `DISCARDED`) and safe garbage collection.

4. **Dynamic Tool Scheduler & Dependency DAG (`chronos.tools`)**:
   - Dynamic schema-driven manifest (zero domain hardcoding).
   - Dependency DAG with selective invalidation: only cancels nodes dependent on modified slots, while preserving reusable sub-results.

5. **Commit Controller & Strict Idempotency (`chronos.commit`)**:
   - 4-phase commit pipeline: `SPECULATIVE` $\rightarrow$ `PREPARE` $\rightarrow$ `CONFIRMATION` $\rightarrow$ `COMMIT`.
   - Idempotency key tracking preventing duplicate state-changing calls across retries, timeouts, or reconnections.

6. **Interruption Hierarchy & Debouncer (`chronos.interruption`)**:
   - **Level 0**: Backchannel ("yeah", "okay") $\rightarrow$ No state mutation.
   - **Level 1**: Slot Correction ("Tomorrow — actually Friday") $\rightarrow$ Surgical slot mutation & selective DAG invalidation.
   - **Level 2**: Goal Change ("Don't book it, just show options") $\rightarrow$ New branch creation.
   - **Level 3**: Explicit Stop ("Cancel that") $\rightarrow$ Immediate tool cancellation.
   - **Level 4**: Irreversible In-Flight Interruption $\rightarrow$ Immediate halt and state reconciliation.
   - ASR token stream debouncing.

7. **Fast Path Floor Controller (`chronos.floor`)**:
   - Low-latency acknowledgment and turn-taking decoupled from heavy reasoning.

8. **Perception & Multimodal Grounding (`chronos.perception`)**:
   - Grounding deictic references ("the cheapest one", "the second flight") to active results.

9. **Evaluation / Replay Harness (`chronos.evaluation`)**:
   - Deterministic scenario runner with fault and stale result injection.
   - Metrics computation: task completion, recovery latency, stale rejection rate, safety score.

10. **Visual Control Plane Dashboard (`chronos.server`)**:
    - Real-time FastAPI + Server-Sent Events (SSE) web inspector.

---

## Quick Start

### 1. Run Automated Tests
```bash
python -m pytest tests/ -v
```

### 2. Launch Real-Time Control Plane Dashboard
```bash
python -m uvicorn chronos.server.app:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.
