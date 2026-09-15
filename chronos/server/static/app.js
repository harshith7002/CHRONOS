// CHRONOS UI Controller & Telemetry Stream

let eventSource = null;

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
    console.warn("SSE disconnected, attempting reconnect...");
    setTimeout(initSSE, 2000);
  };
}

function renderState(state) {
  if (!state) return;

  // Header & Status
  document.getElementById('val-virtual-time').innerText = `${state.virtual_time.toFixed(2)}s`;
  document.getElementById('val-current-snapshot').innerText = state.current_snapshot?.snapshot_id || 'v0';
  document.getElementById('val-current-branch').innerText = state.current_snapshot?.branch_id || 'main';
  document.getElementById('val-commit-status').innerText = state.commit_status || 'IDLE';

  // Metrics
  document.getElementById('val-metric-snapshots').innerText = state.all_snapshots?.length || 0;
  document.getElementById('val-metric-stale').innerText = state.stale_results?.length || 0;
  document.getElementById('val-metric-events').innerText = state.event_count || 0;

  // Intent Slots
  const slotsContainer = document.getElementById('slots-container');
  const slots = state.intent_slots || {};
  if (Object.keys(slots).length === 0) {
    slotsContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">No slots populated yet.</span>';
  } else {
    slotsContainer.innerHTML = Object.entries(slots).map(([k, v]) => `
      <div class="slot-tag">
        <span class="slot-key">${k}:</span>
        <span class="slot-val">${v}</span>
      </div>
    `).join('');
  }

  // Snapshot Lineage
  const metaLabel = document.getElementById('label-snap-meta');
  metaLabel.innerText = `Parent: ${state.current_snapshot?.parent_snapshot_id || 'None'} | Ver: ${state.current_snapshot?.version_number || 0}`;

  const historyEl = document.getElementById('snapshot-history');
  if (state.all_snapshots && state.all_snapshots.length > 0) {
    historyEl.innerHTML = state.all_snapshots.map(s => `
      <div style="margin-bottom: 4px; padding: 2px 4px; ${s.snapshot_id === state.current_snapshot.snapshot_id ? 'color: var(--accent-cyan); font-weight: bold; border-left: 2px solid var(--accent-cyan); padding-left: 6px;' : ''}">
        ${s.snapshot_id} (parent: ${s.parent_snapshot_id || 'root'}) - slots: ${JSON.stringify(s.intent_slots)}
      </div>
    `).join('');
  }

  // Active Calls
  const activeCallsList = document.getElementById('active-calls-list');
  const active = state.active_tool_calls || [];
  if (active.length === 0) {
    activeCallsList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">None</span>';
  } else {
    activeCallsList.innerHTML = active.map(c => `
      <div class="call-card call-active">
        <div style="font-weight: 700; color: var(--accent-cyan);">${c.tool_name}(${c.snapshot_id})</div>
        <div style="font-size: 0.75rem; color: var(--text-secondary);">${JSON.stringify(c.arguments)}</div>
        <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 4px;">Class: ${c.execution_class} | ID: ${c.call_id}</div>
      </div>
    `).join('');
  }

  // Stale & Cancelled Calls
  const staleCallsList = document.getElementById('stale-calls-list');
  const stale = state.stale_results || [];
  const cancelled = state.cancelled_tool_calls || [];

  let html = '';
  if (stale.length > 0) {
    html += stale.map(s => `
      <div class="call-card call-stale">
        <div style="font-weight: 700; color: var(--accent-red);">STALE REJECTED: ${s.tool_name}</div>
        <div style="font-size: 0.75rem; color: #fca5a5;">Origin: ${s.origin_snapshot_id} (rejected by current ${state.current_snapshot.snapshot_id})</div>
      </div>
    `).join('');
  }

  if (cancelled.length > 0) {
    html += cancelled.map(c => `
      <div class="call-card call-cancelled">
        <div style="font-weight: 700; color: var(--accent-amber);">CANCELLED: ${c.tool_name}(${c.snapshot_id})</div>
        <div style="font-size: 0.75rem; color: var(--text-secondary);">${JSON.stringify(c.arguments)}</div>
      </div>
    `).join('');
  }

  if (!html) {
    staleCallsList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">None</span>';
  } else {
    staleCallsList.innerHTML = html;
  }

  // Event Stream
  const eventContainer = document.getElementById('event-stream-container');
  const events = state.recent_events || [];
  eventContainer.innerHTML = events.slice().reverse().map(e => `
    <div class="event-row">
      <div class="event-header">
        <span class="event-type ev-${e.event_type}">${e.event_type}</span>
        <span style="color: var(--text-muted); font-size: 0.7rem;">@ ${e.timestamp.toFixed(2)}s | ${e.snapshot_id}</span>
      </div>
      <div class="event-payload">${JSON.stringify(e.payload)}</div>
    </div>
  `).join('');
}

async function sendInput(text) {
  try {
    const res = await fetch('/api/user_input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    renderState(data.state);
  } catch (e) {
    console.error("sendInput error", e);
  }
}

async function sendCustomInput() {
  const inputEl = document.getElementById('custom-input-text');
  const text = inputEl.value.trim();
  if (text) {
    await sendInput(text);
    inputEl.value = '';
  }
}

document.getElementById('custom-input-text')?.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') sendCustomInput();
});

async function stepTime(delta) {
  try {
    const res = await fetch('/api/step_time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta }),
    });
    const data = await res.json();
    renderState(data.state);
  } catch (e) {
    console.error("stepTime error", e);
  }
}

async function injectStaleDelhi() {
  try {
    const res = await fetch('/api/inject_stale', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        call_id: "call_delhi_old",
        origin_snapshot_id: "v1",
        tool_name: "search_flights",
        output: [{ flight_id: "DEL-999", price: 5000, dest: "Delhi" }]
      }),
    });
    const data = await res.json();
    renderState(data.state);
  } catch (e) {
    console.error("injectStale error", e);
  }
}

async function runFullDemo() {
  try {
    const res = await fetch('/api/run_demo', { method: 'POST' });
    const data = await res.json();
    renderState(data.state);
    alert(`Demo completed! Task completed: ${data.report.task_completed}, Stale rejected: ${data.report.stale_results_rejected}, Safety score: ${data.report.safety_compliance_rate}`);
  } catch (e) {
    console.error("runFullDemo error", e);
  }
}

async function resetState() {
  try {
    const res = await fetch('/api/reset', { method: 'POST' });
    const data = await res.json();
    renderState(data.state);
  } catch (e) {
    console.error("resetState error", e);
  }
}

// Initial fetch & SSE start
window.addEventListener('DOMContentLoaded', () => {
  fetch('/api/state')
    .then(r => r.json())
    .then(renderState)
    .catch(console.error);

  initSSE();
});
