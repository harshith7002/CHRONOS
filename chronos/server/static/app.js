/**
 * CHRONOS ONE | World-Class Visual AI Product Experience Controller
 * Powers animated hero temporal timelines, natural conversational interruptions,
 * signature CHRONOS pulse waves, flight selection, and live SSE telemetry.
 */

let eventSource = null;
let currentHeroStep = "v1"; // "v1", "interrupted", "v2_active"
let currentFlightSelection = { index: 0, price: "₹7,200", time: "08:10", route: "Chennai ➔ Mumbai" };
let activeDestination = "Mumbai";
let activeDate = "Friday, 10 Oct";

// -----------------------------------------------------------------------------
// 1. Hero Temporal Interactive Visualization
// -----------------------------------------------------------------------------
function renderHeroTemporalSVG(state) {
  const svg = document.getElementById("hero-temporal-svg");
  if (!svg) return;

  let content = "";

  if (state === "v1") {
    content = `
      <!-- Base Connecting Stream -->
      <line x1="60" y1="130" x2="380" y2="130" stroke="rgba(255,255,255,0.15)" stroke-width="2" stroke-dasharray="6"/>
      
      <!-- Node: Intent v1 -->
      <g transform="translate(30, 95)">
        <rect width="130" height="70" rx="14" fill="rgba(8, 14, 28, 0.9)" stroke="#00e5ff" stroke-width="2" />
        <circle cx="24" cy="35" r="5" fill="#00e5ff">
          <animate attributeName="r" values="4;7;4" dur="1.5s" repeatCount="indefinite"/>
        </circle>
        <text x="75" y="32" fill="#00e5ff" font-size="11" font-weight="700" text-anchor="middle">SNAPSHOT v1</text>
        <text x="75" y="50" fill="#94a3b8" font-size="10" text-anchor="middle">Destination: Delhi</text>
      </g>

      <!-- Node: Executing Tool -->
      <g transform="translate(230, 95)">
        <rect width="190" height="70" rx="14" fill="rgba(37, 99, 235, 0.15)" stroke="#00e5ff" stroke-width="2" />
        <text x="95" y="32" fill="#fff" font-size="11" font-weight="700" text-anchor="middle">search_flights(v1)</text>
        <text x="95" y="50" fill="#38bdf8" font-size="10" text-anchor="middle">⚡ Executing Async...</text>
      </g>
    `;
  } else if (state === "interrupted") {
    content = `
      <!-- Branch Lines -->
      <path d="M 130 130 Q 180 65 240 65" fill="none" stroke="rgba(245, 158, 11, 0.5)" stroke-width="2" stroke-dasharray="4"/>
      <path d="M 130 130 Q 180 195 240 195" fill="none" stroke="#00e5ff" stroke-width="2"/>

      <!-- Node: Obsolete v1 Branch (Faded / Superseded) -->
      <g transform="translate(20, 100)">
        <rect width="110" height="60" rx="12" fill="rgba(8, 14, 28, 0.9)" stroke="#00e5ff" stroke-width="2" />
        <text x="55" y="35" fill="#00e5ff" font-size="10" font-weight="700" text-anchor="middle">INTENT v1</text>
      </g>

      <g transform="translate(230, 35)">
        <rect width="200" height="60" rx="12" fill="rgba(245, 158, 11, 0.05)" stroke="#f59e0b" stroke-width="1.5" opacity="0.6" />
        <text x="100" y="28" fill="#f59e0b" font-size="10" font-weight="700" text-anchor="middle">search_flights(Delhi)</text>
        <text x="100" y="46" fill="#f59e0b" font-size="9" text-anchor="middle">🛑 SUPERSEDED (Cancelled)</text>
      </g>

      <!-- Node: Active v2 Branch -->
      <g transform="translate(230, 165)">
        <rect width="200" height="60" rx="12" fill="rgba(0, 229, 255, 0.15)" stroke="#00e5ff" stroke-width="2" />
        <circle cx="22" cy="30" r="5" fill="#00e5ff">
          <animate attributeName="r" values="3;7;3" dur="1s" repeatCount="indefinite"/>
        </circle>
        <text x="105" y="28" fill="#fff" font-size="10" font-weight="700" text-anchor="middle">search_flights(Mumbai)</text>
        <text x="105" y="46" fill="#00e5ff" font-size="9" text-anchor="middle">⚡ ACTIVE v2 CONTINUATION</text>
      </g>
    `;
  }

  svg.innerHTML = content;
}

function simulateHeroPulse() {
  currentHeroStep = currentHeroStep === "v1" ? "interrupted" : "v1";
  renderHeroTemporalSVG(currentHeroStep);
}

// -----------------------------------------------------------------------------
// 2. Product Demo: Natural Interruption & Signature Pulse Wave
// -----------------------------------------------------------------------------
function triggerPulseWaveAnimation() {
  const wave = document.getElementById("task-pulse-wave");
  if (wave) {
    wave.classList.remove("trigger");
    void wave.offsetWidth; // Force reflow
    wave.classList.add("trigger");
  }
}

async function handleUserCorrection(correctionText) {
  triggerPulseWaveAnimation();

  const trackerText = document.getElementById("tracker-task-text");
  const trackerVersion = document.getElementById("tracker-version-tag");
  const dateTag = document.getElementById("flight-date-tag");
  const destLabel = document.getElementById("flight-destination-label");
  const chatStream = document.getElementById("chat-messages-container");

  if (correctionText.includes("Saturday")) {
    activeDate = "Saturday, 11 Oct";
    if (dateTag) dateTag.innerText = "Saturday, 11 Oct";
    if (trackerVersion) trackerVersion.innerText = "SNAPSHOT v2";
    if (trackerText) {
      trackerText.innerHTML = `Friday ➔ <span style="color: var(--amber);">Updating...</span> ➔ <strong style="color: var(--emerald);">Saturday ✓ ACTIVE</strong>`;
    }

    appendMsg(chatStream, "user", '"Actually Saturday."');
    setTimeout(() => {
      appendMsg(
        chatStream,
        "assistant",
        'Updated your plan to <strong>Saturday morning</strong> without restarting. Refreshed 3 flight options. Cheapest is Indigo 6E-204 at <strong>₹7,200</strong>.'
      );
    }, 350);

    // Call backend
    await fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Actually Saturday morning" }),
    });

  } else if (correctionText.includes("Delhi")) {
    activeDestination = "Delhi";
    if (destLabel) destLabel.innerText = "Chennai ➔ Delhi";
    if (trackerVersion) trackerVersion.innerText = "SNAPSHOT v3";
    if (trackerText) {
      trackerText.innerHTML = `Mumbai ➔ <span style="color: var(--amber);">Updating...</span> ➔ <strong style="color: var(--emerald);">Delhi ✓ ACTIVE</strong>`;
    }

    const a0 = document.getElementById("airline-name-0");
    const a1 = document.getElementById("airline-name-1");
    const a2 = document.getElementById("airline-name-2");
    if (a0) a0.innerText = "Indigo 6E-502 to Delhi";
    if (a1) a1.innerText = "Air India AI-801 to Delhi";
    if (a2) a2.innerText = "Vistara UK-920 to Delhi";

    appendMsg(chatStream, "user", '"Actually Chennai to Delhi, not Mumbai."');
    setTimeout(() => {
      appendMsg(
        chatStream,
        "assistant",
        'Destination updated to <strong>Delhi</strong>. Cleanly cancelled previous Mumbai routines and fetched direct Delhi flights.'
      );
    }, 350);

    await fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Actually Chennai to Delhi, not Mumbai" }),
    });
  }
}

function appendMsg(container, role, html) {
  if (!container) return;
  const el = document.createElement("div");
  el.className = `msg-bubble ${role}`;
  el.innerHTML = html;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

// -----------------------------------------------------------------------------
// 3. Stale Result Rejection Simulation
// -----------------------------------------------------------------------------
async function triggerStaleInjectionDemo() {
  const shield = document.getElementById("stale-shield-card");
  if (shield) shield.classList.add("show");

  const chatStream = document.getElementById("chat-messages-container");
  appendMsg(
    chatStream,
    "assistant",
    `🛡️ <strong>Late Result Blocked:</strong> An older flight response from your previous request arrived out-of-order, but CHRONOS discarded it because your request had already evolved.`
  );

  // Trigger backend stale injection
  await fetch("/api/inject_stale", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      call_id: "call_v1_stale_delhi",
      origin_snapshot_id: "v1",
      tool_name: "search_flights",
      output: { flight: "OLD-DEL-888", price: 9500 },
    }),
  });
}

// -----------------------------------------------------------------------------
// 4. Flight Selection & 4-Phase Gated Commit
// -----------------------------------------------------------------------------
function selectFlightOption(index, price, time) {
  currentFlightSelection = {
    index,
    price,
    time,
    route: `Chennai ➔ ${activeDestination}`,
  };

  [0, 1, 2].forEach((i) => {
    const card = document.getElementById(`ticket-card-${i}`);
    if (card) card.classList.toggle("selected", i === index);
  });

  const summary = document.getElementById("checkout-route-summary");
  const priceDisplay = document.getElementById("checkout-price-display");
  const btnLabel = document.getElementById("btn-price-label");

  if (summary) summary.innerText = `${currentFlightSelection.route} (${time} · ${activeDate})`;
  if (priceDisplay) priceDisplay.innerText = price;
  if (btnLabel) btnLabel.innerText = price;
}

async function executeGatedCommit() {
  const btn = document.getElementById("btn-commit-booking");
  if (btn) {
    btn.innerHTML = "⏳ Validating Idempotency Key (INV-3)...";
    btn.disabled = true;
  }

  await fetch("/api/step_time", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delta: 0.2 }),
  });

  setTimeout(() => {
    if (btn) {
      btn.innerHTML = "✓ Booking Committed Once · Zero Duplicates";
      btn.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }

    const chatStream = document.getElementById("chat-messages-container");
    appendMsg(
      chatStream,
      "assistant",
      `🎉 <strong>Flight Confirmed!</strong> Your booking for ${currentFlightSelection.route} (${currentFlightSelection.time}) has been safely committed with idempotency protection.`
    );
  }, 450);
}

// -----------------------------------------------------------------------------
// 5. Advanced Inspector (For Engineers) Drawer & SSE Stream
// -----------------------------------------------------------------------------
function toggleEngineerDrawer() {
  const drawer = document.getElementById("engineer-drawer");
  if (drawer) drawer.classList.toggle("open");
}

function initSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/events/stream");

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event) appendRawEvent(data.event);
    } catch (e) {
      console.error("SSE error", e);
    }
  };

  eventSource.onerror = () => {
    setTimeout(initSSE, 3000);
  };
}

function appendRawEvent(evt) {
  const feed = document.getElementById("raw-sse-telemetry-feed");
  if (!feed) return;

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
  const row = document.createElement("div");
  row.style.borderLeft = `2px solid ${col}`;
  row.style.padding = "2px 6px";
  row.innerHTML = `
    <span style="color: ${col}; font-weight: bold;">[${evt.event_type}]</span>
    <span style="color: #64748b;">@${evt.timestamp.toFixed(2)}s (${evt.snapshot_id || "v0"})</span>:
    <span>${JSON.stringify(evt.payload || {})}</span>
  `;
  feed.prepend(row);
}

// -----------------------------------------------------------------------------
// DOM Ready Initialization
// -----------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  renderHeroTemporalSVG("v1");
  initSSE();
});
