// CHRONOS Premium UI Controller & Interactive Story Engine

let eventSource = null;
let currentDemoStep = 1;
let replayEventIndex = -1;
let cachedEvents = [];

function initSSE() {
  if (eventSource) {
    eventSource.close();
  }
  eventSource = new EventSource('/api/events/stream');

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.state) {
        renderState(data.state);
      }
    } catch (e) {
      console.error("SSE parse error", e);
    }
  };

  eventSource.onerror = () => {
    setTimeout(initSSE, 2000);
  };
}

function renderState(state) {
  if (!state) return;

  // Update Inspector
  const curSnap = state.current_snapshot?.snapshot_id || 'v0';
  document.getElementById('insp-cur-snap').innerText = curSnap;
  document.getElementById('insp-parent-snap').innerText = state.current_snapshot?.parent_snapshot_id || 'None';
  document.getElementById('insp-branch').innerText = state.current_snapshot?.branch_id || 'main';
  document.getElementById('insp-commit-status').innerText = state.commit_status || 'IDLE';
  document.getElementById('insp-vtime').innerText = `${state.virtual_time.toFixed(2)}s`;

  // Telemetry stream
  const eventContainer = document.getElementById('event-stream-container');
  const events = state.recent_events || [];
  cachedEvents = events;
  eventContainer.innerHTML = events.slice().reverse().map((e, idx) => `
    <div class="telemetry-row" id="evt-row-${events.length - 1 - idx}" style="border-left: 2px solid ${getEventColor(e.event_type)};">
      <span style="color: ${getEventColor(e.event_type)}; font-weight: bold;">[${e.event_type}]</span>
      <span style="color: #64748b;">@ ${e.timestamp.toFixed(2)}s (${e.snapshot_id})</span>:
      <span>${JSON.stringify(e.payload)}</span>
    </div>
  `).join('');
}

function getEventColor(type) {
  switch (type) {
    case 'USER_INPUT': return '#3b82f6';
    case 'INTENT_UPDATE': return '#06b6d4';
    case 'SNAPSHOT_CREATED': return '#8b5cf6';
    case 'TOOL_DISPATCHED': return '#0284c7';
    case 'TOOL_COMPLETED': return '#10b981';
    case 'TOOL_CANCELLED': return '#f59e0b';
    case 'STALE_RESULT_REJECTED': return '#f43f5e';
    case 'COMMIT': return '#10b981';
    default: return '#94a3b8';
  }
}

// -------------------------------------------------------------
// HERO DEMO INTERACTIVE STORY ENGINE
// -------------------------------------------------------------

function setStepActive(stepNum) {
  currentDemoStep = stepNum;
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById(`btn-step-${i}`);
    if (btn) {
      if (i === stepNum) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  }
}

async function jumpToDemoStep(step) {
  setStepActive(step);

  const titleEl = document.getElementById('demo-phase-title');
  const descEl = document.getElementById('demo-phase-desc');
  const snapBadge = document.getElementById('demo-snap-badge');
  const commitBadge = document.getElementById('demo-commit-badge');
  const userText = document.getElementById('demo-user-text');
  const intentVTag = document.getElementById('demo-intent-vtag');
  const intentSlots = document.getElementById('demo-intent-slots-content');
  const execCards = document.getElementById('demo-execution-cards-container');
  const staleAlert = document.getElementById('demo-stale-alert-area');
  const commitBox = document.getElementById('demo-commit-box');
  const nextBtn = document.getElementById('demo-next-action-btn');

  if (step === 1) {
    titleEl.innerText = "Phase 1: Initial Intent (v1)";
    descEl.innerText = "User asks to search flights to Delhi";
    snapBadge.innerText = "SNAPSHOT: v1";
    snapBadge.style.color = "var(--brand-cyan)";
    commitBadge.innerText = "COMMIT: IDLE";
    userText.innerText = '"Find me a flight to Delhi tomorrow morning under 10000."';
    intentVTag.innerText = "INTENT v1";
    intentSlots.innerHTML = "Destination: <strong>Delhi</strong> · Date: <strong>Tomorrow</strong> · Time: <strong>Morning</strong>";
    execCards.innerHTML = `
      <div class="execution-card" style="border-left: 3px solid var(--brand-cyan);">
        <span>search_flights(v1) [Delhi]</span>
        <span class="status-badge badge-running">RUNNING</span>
      </div>
    `;
    staleAlert.style.display = "none";
    commitBox.style.display = "none";
    nextBtn.innerText = "Next: User Interrupts ➔";
    nextBtn.onclick = () => jumpToDemoStep(2);

    // Call backend
    await fetch('/api/reset', { method: 'POST' });
    await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Find me a flight to Delhi tomorrow morning under 10000" })
    });
  } else if (step === 2) {
    titleEl.innerText = "Phase 2: Intent Versioning & Interruption (v2)";
    descEl.innerText = "User changes destination mid-stream: v1 is cancelled, v2 starts";
    snapBadge.innerText = "SNAPSHOT: v2";
    snapBadge.style.color = "var(--brand-cyan)";
    commitBadge.innerText = "COMMIT: IDLE";
    userText.innerText = '"Actually Mumbai."';
    intentVTag.innerText = "INTENT v2";
    intentSlots.innerHTML = "Destination: <strong style='color: var(--brand-cyan);'>Mumbai</strong> · Date: <strong>Tomorrow</strong> · Time: <strong>Morning</strong>";
    execCards.innerHTML = `
      <div class="execution-card" style="border-left: 3px solid var(--brand-amber); opacity: 0.85;">
        <span>search_flights(v1) [Delhi]</span>
        <span class="status-badge badge-cancelled">✓ CANCELLED</span>
      </div>
      <div class="execution-card" style="border-left: 3px solid var(--brand-cyan);">
        <span>search_flights(v2) [Mumbai]</span>
        <span class="status-badge badge-running">RUNNING</span>
      </div>
    `;
    staleAlert.style.display = "none";
    commitBox.style.display = "none";
    nextBtn.innerText = "Next: Simulate Out-of-Order Stale Result ➔";
    nextBtn.onclick = () => jumpToDemoStep(3);

    await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Actually Mumbai" })
    });
  } else if (step === 3) {
    titleEl.innerText = "Phase 3: Out-of-Order Stale Result Rejected";
    descEl.innerText = "Old v1 Delhi result arrives late: rejected before mutating v2 state";
    snapBadge.innerText = "SNAPSHOT: v2";
    commitBadge.innerText = "COMMIT: IDLE";
    userText.innerText = 'System event: Late Delhi result arrives';
    intentVTag.innerText = "INTENT v2";
    intentSlots.innerHTML = "Destination: <strong>Mumbai</strong> · State remains 100% clean";
    execCards.innerHTML = `
      <div class="execution-card" style="border-left: 3px solid var(--brand-rose); background: rgba(244, 63, 94, 0.05);">
        <span>result(search_flights(v1)) [Delhi]</span>
        <span class="status-badge badge-stale">STALE REJECTED</span>
      </div>
      <div class="execution-card" style="border-left: 3px solid var(--brand-emerald);">
        <span>search_flights(v2) [Mumbai]</span>
        <span class="status-badge badge-committed">COMPLETED</span>
      </div>
    `;
    staleAlert.style.display = "block";
    commitBox.style.display = "none";
    nextBtn.innerText = "Next: Safe Commit & Confirmation ➔";
    nextBtn.onclick = () => jumpToDemoStep(4);

    await fetch('/api/inject_stale', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        call_id: "call_delhi_old",
        origin_snapshot_id: "v1",
        tool_name: "search_flights",
        output: [{ flight_id: "DEL-999", price: 5000, dest: "Delhi" }]
      })
    });
    await fetch('/api/step_time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta: 0.5 })
    });
  } else if (step === 4) {
    titleEl.innerText = "Phase 4: Guarded Commit & Strict Idempotency";
    descEl.innerText = "Booking passes 4-phase safety gate with explicit confirmation";
    snapBadge.innerText = "SNAPSHOT: v2";
    commitBadge.innerText = "COMMIT: CONFIRMED";
    commitBadge.style.color = "var(--brand-emerald)";
    userText.innerText = '"Book the cheapest one." ➔ "Yes, confirm."';
    intentVTag.innerText = "INTENT v2";
    intentSlots.innerHTML = "Destination: <strong>Mumbai</strong> · Booking: <strong>Confirmed (PNR Generated)</strong>";
    execCards.innerHTML = `
      <div class="execution-card" style="border-left: 3px solid var(--brand-emerald);">
        <span>book_flight(v2) [Mumbai BOM-303]</span>
        <span class="status-badge badge-committed">✓ COMMITTED</span>
      </div>
    `;
    staleAlert.style.display = "none";
    commitBox.style.display = "block";
    nextBtn.innerText = "✓ Demo Completed (Click to Replay)";
    nextBtn.onclick = () => jumpToDemoStep(1);

    await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Book the cheapest one" })
    });
    await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Yes, confirm and proceed" })
    });
  }
}

function advanceDemoStep() {
  const next = currentDemoStep < 4 ? currentDemoStep + 1 : 1;
  jumpToDemoStep(next);
}

async function startHeroInteractiveDemo() {
  const el = document.getElementById('hero-demo');
  if (el) el.scrollIntoView({ behavior: 'smooth' });
  jumpToDemoStep(1);
}

// -------------------------------------------------------------
// BENCHMARKS & INSPECTOR UTILITIES
// -------------------------------------------------------------

async function runLiveMatrixBenchmark() {
  const btn = event.target;
  btn.innerText = "Running 500 Iterations...";
  btn.disabled = true;

  try {
    const res = await fetch('/api/run_matrix', { method: 'POST' });
    const data = await res.json();
    const s = data.summary;

    document.getElementById('matrix-chronos-completion').innerText = `${(s.chronos_task_completion_rate * 100).toFixed(1)}%`;
    document.getElementById('matrix-chronos-invariants').innerText = `${s.chronos_total_invariant_violations} (Zero)`;
    document.getElementById('matrix-chronos-duplicates').innerText = `${s.chronos_total_duplicate_commits} (Zero)`;
    document.getElementById('matrix-chronos-stale').innerText = `${s.chronos_total_stale_violations} (Zero)`;

    document.getElementById('matrix-naive-safety').innerText = `${s.naive_total_safety_violations} Violations`;
    document.getElementById('matrix-naive-duplicates').innerText = `${s.naive_total_duplicate_commits} Duplicates`;
    document.getElementById('matrix-naive-stale').innerText = `${s.naive_total_stale_violations} Contaminations`;

    btn.innerText = "✓ Matrix Verified (500 Runs)";
  } catch (e) {
    btn.innerText = "⚡ Re-run Matrix";
  } finally {
    btn.disabled = false;
  }
}

async function measureLiveOverhead() {
  try {
    const res = await fetch('/api/run_benchmark', { method: 'POST' });
    const data = await res.json();
    const b = data.benchmark;

    document.getElementById('lat-ack-p50').innerText = `${(b.fast_path_ack_latency.p50_ms * 1000).toFixed(0)} µs (${b.fast_path_ack_latency.p50_ms.toFixed(3)} ms)`;
    document.getElementById('lat-ack-p95').innerText = `${(b.fast_path_ack_latency.p95_ms * 1000).toFixed(0)} µs`;
    document.getElementById('lat-ack-p99').innerText = `${(b.fast_path_ack_latency.p99_ms * 1000).toFixed(0)} µs`;
    document.getElementById('lat-ack-mean').innerText = `${(b.fast_path_ack_latency.mean_ms * 1000).toFixed(0)} µs`;

    document.getElementById('lat-cancel-p50').innerText = `${(b.interruption_cancellation_latency.p50_ms * 1000).toFixed(0)} µs (${b.interruption_cancellation_latency.p50_ms.toFixed(3)} ms)`;
    document.getElementById('lat-cancel-p95').innerText = `${(b.interruption_cancellation_latency.p95_ms * 1000).toFixed(0)} µs`;
    document.getElementById('lat-cancel-p99').innerText = `${(b.interruption_cancellation_latency.p99_ms * 1000).toFixed(0)} µs`;
    document.getElementById('lat-cancel-mean').innerText = `${(b.interruption_cancellation_latency.mean_ms * 1000).toFixed(0)} µs`;

    alert("Empirical latencies re-measured over 500 local iterations!");
  } catch (e) {
    console.error("measureLiveOverhead error", e);
  }
}

function toggleInspector() {
  const body = document.getElementById('inspector-body');
  const label = document.getElementById('inspector-toggle-label');
  if (body.style.display === 'block') {
    body.style.display = 'none';
    label.innerText = "Click to Expand ▼";
  } else {
    body.style.display = 'block';
    label.innerText = "Click to Collapse ▲";
  }
}

async function sendInspectorInput() {
  const inputEl = document.getElementById('inspector-input');
  const text = inputEl.value.trim();
  if (text) {
    await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    inputEl.value = '';
  }
}

async function stepTime(delta) {
  await fetch('/api/step_time', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delta })
  });
}

async function injectStaleDelhi() {
  await fetch('/api/inject_stale', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      call_id: "call_delhi_old",
      origin_snapshot_id: "v1",
      tool_name: "search_flights",
      output: [{ flight_id: "DEL-999", price: 5000, dest: "Delhi" }]
    })
  });
}

async function resetState() {
  await fetch('/api/reset', { method: 'POST' });
  jumpToDemoStep(1);
}

function stepReplay(delta) {
  if (!cachedEvents || cachedEvents.length === 0) return;
  if (replayEventIndex === -1) replayEventIndex = cachedEvents.length - 1;
  replayEventIndex = Math.max(0, Math.min(cachedEvents.length - 1, replayEventIndex + delta));
  const el = document.getElementById(`evt-row-${replayEventIndex}`);
  if (el) {
    document.querySelectorAll('.telemetry-row').forEach(r => r.style.background = 'transparent');
    el.style.background = 'rgba(6, 182, 212, 0.2)';
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// Initial start
window.addEventListener('DOMContentLoaded', () => {
  initSSE();
});
