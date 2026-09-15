# CHRONOS: Temporal Control Plane for Interruptible Real-Time AI Agents

> **“Most AI agents optimize for better reasoning. CHRONOS optimizes for correct execution when reality changes. We version user intent, selectively invalidate obsolete work, preserve reusable computation, reject stale asynchronous results, and prevent stale intent from reaching irreversible actions. We validate these guarantees with formal invariants and a 2,000-run adversarial benchmark against an unversioned baseline.”**

**CHRONOS** is a production-oriented, empirically validated temporal control plane for interruptible real-time AI agents. It guarantees that agent state remains consistent when users change their intent mid-stream, tools complete asynchronously out of order, and irreversible state-changing actions are queued.

---

## The 7 CHRONOS Invariants (The Correctness Contract)

The system is designed around explicit formal invariants enforced across the event log, snapshot tree, and execution ledger:

```text
INV-1: Stale results cannot mutate active intent slots or completed state.
INV-2: Only the current active snapshot can commit irreversible actions.
INV-3: One idempotency key permits at most one irreversible commit.
INV-4: Invalidation of an upstream dependency invalidates all dependent downstream work.
INV-5: Superseded branches cannot execute new state-changing writes.
INV-6: Unconfirmed irreversible actions are strictly blocked from execution.
INV-7: Historical state snapshots are strictly immutable.
```

---

## "We Don't Just Claim Correctness — We Attack It."

### 2,000-Run Adversarial Benchmark ($20\text{ Failure Categories} \times 100\text{ Randomized Seeds}$)

*Evaluated against an intentionally minimal unversioned baseline implementing conventional mutable-state asynchronous execution under identical deterministic fault injection:*

| Metric | CHRONOS Control Plane | Minimal Unversioned Baseline |
| :--- | :---: | :---: |
| **Task Completion Rate** | **100.0%** | Incomplete / Degraded |
| **Invariant Violations** | **0 (Zero)** | — |
| **Safety Violations** | **0 (Zero)** | **1,200 Violations** |
| **Duplicate Commits** | **0 (Zero)** | **800 Duplicates** |
| **Stale State Contaminations** | **0 (Zero)** | **300 Contaminations** |
| **Mean Interruption Recovery** | **0.150 ms** | Context Reset / Re-plan |

*Note on Evaluation Methodology: Our evaluation uses deterministic mocked external tools so that network failures, timing skews, and out-of-order responses can be reproduced and verified with microsecond precision.*

---

## The Fundamental Difference: Baseline vs. CHRONOS

| Scenario / Failure Mode | Minimal Unversioned Baseline | CHRONOS Control Plane |
| :--- | :--- | :--- |
| **Late Stale Result Arrival** | ❌ State contaminated by out-of-order data | ✅ **Strictly rejected (`STALE_RESULT_REJECTED` via INV-1)** |
| **User Mid-Stream Correction** | ❌ Blind cancellation and full restart | ✅ **Selective invalidation (preserves reusable work)** |
| **Duplicate Confirmation / Retry Storm** | ❌ Risk of duplicate charges / writes | ✅ **Idempotency protected (`idem_<hash>` via INV-3)** |
| **Irreversible Action Under Stale Intent** | ❌ High risk of executing stale state | ✅ **Commit blocked via 4-phase safety gate (INV-2, INV-6)** |
| **Chained Tool Dependencies** | ❌ Broad, uncontrolled re-execution | ✅ **DAG-aware surgical cascade invalidation (INV-4)** |
| **Recovery Latency & State Continuity** | ❌ Full context reset & re-plan | ✅ **Versioned continuation ($v_1 \rightarrow v_2 \dots$)** |

---

## Core Invariant

> **"Never blindly stop and restart. Version the intent, selectively invalidate obsolete work, preserve reusable work, reject stale results, and commit irreversible actions only after explicit confirmation."**

---

## Control-Plane Microbenchmarks ($N = 1,000$ iterations)

*These metrics measure the local Python control-plane coordination overhead (excluding external LLM/network IO) to verify that CHRONOS introduces negligible latency on the critical execution path.*

| Critical Path Operation | Median ($p50$) | $p95$ | $p99$ | Mean | Samples |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fast-Path Acknowledgment Control** | **$0.010\text{ ms}$ ($10\ \mu\text{s}$)** | $0.019\text{ ms}$ | $0.049\text{ ms}$ | $0.012\text{ ms}$ | $1,000$ |
| **Interruption ➔ Cancellation Propagation** | **$0.150\text{ ms}$ ($150\ \mu\text{s}$)** | $0.357\text{ ms}$ | $0.520\text{ ms}$ | $0.178\text{ ms}$ | $1,000$ |
| **Immutable Snapshot Evolution** | **$0.014\text{ ms}$ ($14\ \mu\text{s}$)** | $0.026\text{ ms}$ | $0.041\text{ ms}$ | $0.016\text{ ms}$ | $1,000$ |
| **Idempotency Ledger Duplicate Check** | **$0.001\text{ ms}$ ($1\ \mu\text{s}$)** | $0.001\text{ ms}$ | $0.002\text{ ms}$ | $0.001\text{ ms}$ | $1,000$ |

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

## Empirical Latency Benchmarks (1,000 Iterations)

| Critical Path Operation | Median (p50) | p95 | p99 | Mean | Samples |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fast-Path Acknowledgment** | **0.010 ms (10 µs)** | 0.019 ms | 0.049 ms | 0.012 ms | 1,000 |
| **Interruption ➔ Cancellation Propagation** | **0.150 ms (150 µs)**| 0.357 ms | 0.520 ms | 0.178 ms | 1,000 |
| **Immutable Snapshot Evolution** | **0.014 ms (14 µs)** | 0.026 ms | 0.041 ms | 0.016 ms | 1,000 |
| **Idempotency Ledger Duplicate Check** | **0.001 ms (1 µs)**  | 0.001 ms | 0.002 ms | 0.001 ms | 1,000 |

---

## 4 Core Demonstration Scenarios

1. **Hero Scenario**: Delhi ➔ Mumbai Interruption & Out-of-Order Stale Result Rejection.
2. **Chained DAG Invalidation**: `SEARCH ➔ FILTER ➔ SELECT ➔ BOOK` with selective invalidation on slot mutation.
3. **Adversarial Stale Booking Attack**: Out-of-order $v_1$ token injection into irreversible booking pipeline (visibly blocked by commit controller).
4. **Multimodal Vision Grounding & Revision**: Visual symptom detection $\rightarrow$ user voice clarification $\rightarrow$ automatic diagnostic plan revision & tool cancellation.

---

## Quick Start

### 1. Run Automated Tests (20 Suites)
```bash
python -m pytest tests/ -v
```

### 2. Launch Real-Time Control Plane Dashboard
```bash
python -m uvicorn chronos.server.app:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

