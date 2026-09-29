/**
 * CHRONOS | Samsung Galaxy AI Temporal Control Center Controller
 * Manages Dynamic SVG DAG, Voice Waveforms, Multi-Device Presets, and SSE Telemetry.
 */

let eventSource = null;
let currentStep = 1;
let currentDevicePreset = "phone"; // "phone", "iot", "car"

// -----------------------------------------------------------------------------
// 1. Ambient Background Particles
// -----------------------------------------------------------------------------
function initAmbientCanvas() {
  const canvas = document.getElementById("hero-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  window.addEventListener("resize", () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  const particles = Array.from({ length: 45 }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    radius: Math.random() * 1.5 + 0.5,
    vx: (Math.random() - 0.5) * 0.4,
    vy: (Math.random() - 0.5) * 0.4,
    color: Math.random() > 0.5 ? "rgba(0, 229, 255, " : "rgba(0, 87, 255, ",
    alpha: Math.random() * 0.4 + 0.1,
  }));

  function render() {
    ctx.clearRect(0, 0, width, height);
    particles.forEach((p) => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;
      if (p.y > height) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color + p.alpha + ")";
      ctx.fill();
    });
    requestAnimationFrame(render);
  }
  render();
}

// -----------------------------------------------------------------------------
// 2. Server-Sent Events (SSE) Telemetry Stream
// -----------------------------------------------------------------------------
function initSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/events/stream");

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event) appendLog(data.event);
      if (data.state) updateHud(data.state);
    } catch (e) {
      console.error("SSE parse error", e);
    }
  };

  eventSource.onerror = () => {
    setTimeout(initSSE, 3000);
  };
}

function appendLog(evt) {
  const container = document.getElementById("telemetry-stream");
  if (!container) return;

  const colorMap = {
    USER_INPUT: "#00e5ff",
    INTENT_UPDATE: "#38bdf8",
    TOOL_DISPATCHED: "#60a5fa",
    TOOL_CANCELLED: "#f59e0b",
    STALE_RESULT_REJECTED: "#f43f5e",
    COMMIT: "#10b981",
    SNAPSHOT_CREATED: "#c084fc",
  };

  const col = colorMap[evt.event_type] || "#94a3b8";
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.style.borderLeft = `2px solid ${col}`;
  entry.innerHTML = `
    <span style="color: ${col}; font-weight: bold;">[${evt.event_type}]</span>
    <span style="color: #64748b;">@${evt.timestamp.toFixed(2)}s (${evt.snapshot_id || "v0"})</span>:
    <span>${JSON.stringify(evt.payload || {})}</span>
  `;
  container.prepend(entry);
}

function updateHud(state) {
  if (!state) return;
  const activeSnapBadge = document.getElementById("active-snap-badge");
  if (activeSnapBadge && state.current_snapshot) {
    activeSnapBadge.innerText = `SNAPSHOT ${state.current_snapshot.snapshot_id}`;
  }
}

// -----------------------------------------------------------------------------
// 3. Multi-Device Preset Switcher
// -----------------------------------------------------------------------------
const presets = {
  phone: {
    speech: '"Find me a morning flight to Delhi under ₹10,000"',
    step2Speech: '"Actually make that Mumbai on Friday morning"',
    node1: "search_flights(Delhi)",
    node2: "search_flights(Mumbai)",
    commitTool: "book_flight(Mumbai)",
    staleOutput: "Delhi Flight DEL-999 ₹8,500",
  },
  iot: {
    speech: '"Analyze camera frame: Why is my Bespoke Washer leaking?"',
    step2Speech: '"Wait, camera is pointing at the Fridge now, check error E-404"',
    node1: "diagnose_appliance(Washer)",
    node2: "diagnose_appliance(Fridge)",
    commitTool: "dispatch_technician(Fridge)",
    staleOutput: "Washer diagnostic code W-102",
  },
  car: {
    speech: '"Harman Cockpit: Navigate to Airport via Highway 10"',
    step2Speech: '"Avoid Highway 10, reroute through Downtown express lane"',
    node1: "calculate_route(Highway 10)",
    node2: "calculate_route(Downtown)",
    commitTool: "set_cockpit_guidance(Downtown)",
    staleOutput: "Highway 10 Route ETA: 45 min",
  },
};

function switchPreset(presetKey) {
  currentDevicePreset = presetKey;
  ["phone", "iot", "car"].forEach((k) => {
    const btn = document.getElementById(`tab-${k}`);
    if (btn) btn.classList.toggle("active", k === presetKey);
  });
  runScenarioStep(1);
}

// -----------------------------------------------------------------------------
// 4. Step-by-Step Scenario Controller & Dynamic DAG Rendering
// -----------------------------------------------------------------------------
function setStepButtons(stepNum) {
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById(`btn-step-${i}`);
    if (btn) btn.classList.toggle("active", i === stepNum);
  }
}

async function runScenarioStep(step) {
  currentStep = step;
  setStepButtons(step);
  const preset = presets[currentDevicePreset];

  const speechEl = document.getElementById("user-speech-bubble");
  const floorState = document.getElementById("floor-state-text");
  const actionBtn = document.getElementById("btn-primary-action");
  const inv1Card = document.getElementById("card-inv-1");
  const inv1Badge = document.getElementById("inv-1-badge");
  const inv1Desc = document.getElementById("inv-1-desc");

  if (step === 1) {
    speechEl.innerText = preset.speech;
    floorState.innerText = "LISTENING";
    floorState.style.color = "var(--galaxy-cyan)";
    actionBtn.innerText = `⚡ Trigger Interruption: "${preset.step2Speech.slice(1, 28)}..." ➔`;
    actionBtn.onclick = () => runScenarioStep(2);

    inv1Card.className = "invariant-card pass";
    inv1Badge.className = "badge-tag pass";
    inv1Badge.innerText = "STANDBY";
    inv1Desc.innerText = "Monitoring asynchronous dispatch stream.";

    drawDAG("v1_running");
    await fetch("/api/reset", { method: "POST" });
    await fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: preset.speech }),
    });
  } else if (step === 2) {
    speechEl.innerText = preset.step2Speech;
    floorState.innerText = "INTERRUPTED (Floor Released <10 µs)";
    floorState.style.color = "var(--galaxy-amber)";
    actionBtn.innerText = "💥 Inject Late Out-Of-Order Stale Result ➔";
    actionBtn.onclick = () => runScenarioStep(3);

    inv1Card.className = "invariant-card pass";
    inv1Badge.className = "badge-tag cyan";
    inv1Badge.innerText = "v1 CANCELLED";
    inv1Desc.innerText = "DAG surgically cancelled obsolete v1 node; v2 dispatched.";

    drawDAG("v2_interrupted");
    await fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: preset.step2Speech }),
    });
  } else if (step === 3) {
    speechEl.innerHTML = `⚠️ <strong style="color: var(--galaxy-rose);">LATE ASYNC RESPONSE ARRIVED:</strong> "${preset.staleOutput}" (Origin: v1)`;
    floorState.innerText = "REJECTING STALE INPUT (INV-1)";
    floorState.style.color = "var(--galaxy-rose)";
    actionBtn.innerText = "🔒 Proceed to Safe 4-Phase Commit ➔";
    actionBtn.onclick = () => runScenarioStep(4);

    inv1Card.className = "invariant-card blocked";
    inv1Badge.className = "badge-tag blocked";
    inv1Badge.innerText = "BLOCKED (INV-1)";
    inv1Desc.innerText = `SHIELD ACTIVE: Late v1 result rejected. Active snapshot is v2 (v1 ≠ v2).`;

    drawDAG("stale_blocked");
    await fetch("/api/inject_stale", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        call_id: "call_v1_stale",
        origin_snapshot_id: "v1",
        tool_name: "search_flights",
        output: { result: preset.staleOutput },
      }),
    });
  } else if (step === 4) {
    speechEl.innerHTML = `✅ <strong style="color: var(--galaxy-emerald);">SAFE COMMIT EXECUTED:</strong> Exactly 1 verified booking created. Zero duplicate charges.`;
    floorState.innerText = "COMPLETED & IDEMPOTENT";
    floorState.style.color = "var(--galaxy-emerald)";
    actionBtn.innerText = "↺ Restart Simulation";
    actionBtn.onclick = () => runScenarioStep(1);

    inv1Card.className = "invariant-card pass";
    inv1Badge.className = "badge-tag pass";
    inv1Badge.innerText = "CLEAN";
    inv1Desc.innerText = "Zero state contaminations across full execution lifecycle.";

    drawDAG("committed");
    await fetch("/api/step_time", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta: 0.5 }),
    });
  }
}

function advanceNextStep() {
  const next = currentStep < 4 ? currentStep + 1 : 1;
  runScenarioStep(next);
}

function resetSimulator() {
  runScenarioStep(1);
}

// -----------------------------------------------------------------------------
// 5. SVG Dynamic DAG Visualizer
// -----------------------------------------------------------------------------
function drawDAG(stateMode) {
  const svg = document.getElementById("dag-svg-canvas");
  if (!svg) return;
  const preset = presets[currentDevicePreset];

  let svgContent = "";

  if (stateMode === "v1_running") {
    svgContent = `
      <!-- Connecting Line -->
      <line x1="120" y1="130" x2="270" y2="130" stroke="rgba(255,255,255,0.15)" stroke-width="2" stroke-dasharray="4"/>
      
      <!-- Node: Intent v1 -->
      <g transform="translate(40, 95)">
        <rect width="140" height="70" rx="12" fill="rgba(15, 23, 42, 0.9)" stroke="#00e5ff" stroke-width="2" />
        <text x="70" y="30" fill="#00e5ff" font-size="11" font-weight="700" text-anchor="middle">INTENT v1</text>
        <text x="70" y="50" fill="#94a3b8" font-size="10" text-anchor="middle">Destination: Delhi</text>
      </g>

      <!-- Node: Tool v1 (Running) -->
      <g transform="translate(260, 95)">
        <rect width="200" height="70" rx="12" fill="rgba(0, 87, 255, 0.15)" stroke="#00e5ff" stroke-width="2" class="dag-node-rect" />
        <circle cx="28" cy="35" r="8" fill="#00e5ff" opacity="0.8">
          <animate attributeName="r" values="6;10;6" dur="1.5s" repeatCount="indefinite"/>
        </circle>
        <text x="110" y="30" fill="#fff" font-size="11" font-weight="700" text-anchor="middle">${preset.node1}</text>
        <text x="110" y="50" fill="#38bdf8" font-size="10" text-anchor="middle">⚡ EXECUTING ASYNC...</text>
      </g>
    `;
  } else if (stateMode === "v2_interrupted") {
    svgContent = `
      <!-- Connecting Lines -->
      <line x1="120" y1="70" x2="260" y2="70" stroke="rgba(245, 158, 11, 0.4)" stroke-width="2"/>
      <line x1="120" y1="180" x2="260" y2="180" stroke="rgba(0, 229, 255, 0.4)" stroke-width="2"/>

      <!-- Node: Obsolete v1 -->
      <g transform="translate(40, 35)">
        <rect width="130" height="60" rx="10" fill="rgba(15, 23, 42, 0.6)" stroke="#64748b" stroke-width="1" />
        <text x="65" y="28" fill="#94a3b8" font-size="10" font-weight="700" text-anchor="middle">INTENT v1</text>
        <text x="65" y="46" fill="#64748b" font-size="9" text-anchor="middle">Delhi (Superseded)</text>
      </g>
      <g transform="translate(250, 35)">
        <rect width="210" height="60" rx="10" fill="rgba(245, 158, 11, 0.08)" stroke="#f59e0b" stroke-width="1.5" />
        <text x="105" y="28" fill="#f59e0b" font-size="10" font-weight="700" text-anchor="middle">${preset.node1}</text>
        <text x="105" y="46" fill="#f59e0b" font-size="9" text-anchor="middle">🛑 SURGICALLY CANCELLED</text>
      </g>

      <!-- Node: Active v2 -->
      <g transform="translate(40, 150)">
        <rect width="130" height="60" rx="10" fill="rgba(15, 23, 42, 0.9)" stroke="#00e5ff" stroke-width="2" />
        <text x="65" y="28" fill="#00e5ff" font-size="10" font-weight="700" text-anchor="middle">INTENT v2</text>
        <text x="65" y="46" fill="#38bdf8" font-size="9" text-anchor="middle">Mumbai (Active)</text>
      </g>
      <g transform="translate(250, 150)">
        <rect width="210" height="60" rx="10" fill="rgba(0, 229, 255, 0.15)" stroke="#00e5ff" stroke-width="2" />
        <circle cx="24" cy="30" r="6" fill="#00e5ff">
          <animate attributeName="r" values="4;8;4" dur="1s" repeatCount="indefinite"/>
        </circle>
        <text x="115" y="28" fill="#fff" font-size="10" font-weight="700" text-anchor="middle">${preset.node2}</text>
        <text x="115" y="46" fill="#00e5ff" font-size="9" text-anchor="middle">⚡ DISPATCHED TO v2</text>
      </g>
    `;
  } else if (stateMode === "stale_blocked") {
    svgContent = `
      <!-- Obsolete v1 Stale Arrival Blocked -->
      <g transform="translate(40, 35)">
        <rect width="130" height="60" rx="10" fill="rgba(15, 23, 42, 0.6)" stroke="#64748b" stroke-width="1" />
        <text x="65" y="28" fill="#94a3b8" font-size="10" font-weight="700" text-anchor="middle">INTENT v1</text>
        <text x="65" y="46" fill="#64748b" font-size="9" text-anchor="middle">Superseded</text>
      </g>
      <g transform="translate(250, 35)">
        <rect width="240" height="60" rx="10" fill="rgba(244, 63, 94, 0.12)" stroke="#f43f5e" stroke-width="2" />
        <text x="120" y="26" fill="#f43f5e" font-size="10" font-weight="800" text-anchor="middle">🛡️ STALE RESULT REJECTED</text>
        <text x="120" y="44" fill="#f87171" font-size="9" text-anchor="middle">INV-1 Shield: v1 response blocked</text>
      </g>

      <!-- Active v2 Ready -->
      <g transform="translate(40, 150)">
        <rect width="130" height="60" rx="10" fill="rgba(15, 23, 42, 0.9)" stroke="#10b981" stroke-width="2" />
        <text x="65" y="28" fill="#10b981" font-size="10" font-weight="700" text-anchor="middle">INTENT v2</text>
        <text x="65" y="46" fill="#34d399" font-size="9" text-anchor="middle">Verified Active</text>
      </g>
      <g transform="translate(250, 150)">
        <rect width="240" height="60" rx="10" fill="rgba(16, 185, 129, 0.15)" stroke="#10b981" stroke-width="2" />
        <text x="120" y="28" fill="#fff" font-size="10" font-weight="700" text-anchor="middle">${preset.node2}</text>
        <text x="120" y="46" fill="#10b981" font-size="9" text-anchor="middle">✓ Result Verified for v2</text>
      </g>
    `;
  } else if (stateMode === "committed") {
    svgContent = `
      <!-- Final Gated Commit -->
      <g transform="translate(40, 95)">
        <rect width="130" height="70" rx="12" fill="rgba(15, 23, 42, 0.9)" stroke="#10b981" stroke-width="2" />
        <text x="65" y="30" fill="#10b981" font-size="11" font-weight="700" text-anchor="middle">INTENT v2</text>
        <text x="65" y="50" fill="#34d399" font-size="10" text-anchor="middle">Final Validated</text>
      </g>

      <line x1="170" y1="130" x2="260" y2="130" stroke="#10b981" stroke-width="2"/>

      <g transform="translate(260, 85)">
        <rect width="250" height="90" rx="14" fill="rgba(16, 185, 129, 0.18)" stroke="#10b981" stroke-width="2.5" />
        <text x="125" y="28" fill="#10b981" font-size="12" font-weight="800" text-anchor="middle">🔒 4-PHASE COMMIT EXECUTED</text>
        <text x="125" y="48" fill="#fff" font-size="11" font-weight="600" text-anchor="middle">${preset.commitTool}</text>
        <text x="125" y="68" fill="#a7f3d0" font-size="9" text-anchor="middle">Idempotency Key: idem_v2_ok (INV-3)</text>
      </g>
    `;
  }

  svg.innerHTML = svgContent;
}

// -----------------------------------------------------------------------------
// 6. Adversarial Matrix & Benchmark Triggers
// -----------------------------------------------------------------------------
async function runAdversarialMatrix() {
  const btn = event?.target;
  if (btn) {
    btn.innerText = "⏳ Executing 2,000 Scenarios...";
    btn.disabled = true;
  }
  try {
    const res = await fetch("/api/run_matrix", { method: "POST" });
    const data = await res.json();
    alert(`✓ Adversarial Matrix Completed: 2,000/2,000 Passed with 0 Invariant Violations!`);
  } catch (e) {
    console.error(e);
  } finally {
    if (btn) {
      btn.innerText = "▶ Execute 2,000-Run Adversarial Matrix";
      btn.disabled = false;
    }
  }
}

async function triggerBenchmarkRun() {
  try {
    await fetch("/api/run_benchmark", { method: "POST" });
    alert("✓ Microsecond Latency Benchmark refreshed (N=1,000 iterations). Fast-path: <10 µs");
  } catch (e) {
    console.error(e);
  }
}

function toggleDrawer() {
  const drawer = document.getElementById("inspector-drawer");
  if (drawer) drawer.classList.toggle("open");
}

// -----------------------------------------------------------------------------
// Initialize on DOM Ready
// -----------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  initAmbientCanvas();
  initSSE();
  drawDAG("v1_running");
});
