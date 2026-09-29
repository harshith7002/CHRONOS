/**
 * CHRONOS ONE | Practical Interactive AI Product Demo Controller
 * Powers natural conversational flows, 3 interactive modes, live plan revisions,
 * stale result rejection demonstrations, and the advanced technical inspector.
 */

let eventSource = null;
let currentSelectedFlight = { index: 0, price: "₹7,200", time: "08:10", route: "Chennai ➔ Mumbai" };
let currentTravelDestination = "Mumbai";
let currentTravelDate = "Friday, 10 Oct";

// -----------------------------------------------------------------------------
// 1. Mode Switcher (TRAVEL, HOME, DRIVE)
// -----------------------------------------------------------------------------
function switchMode(modeKey) {
  const modes = ["travel", "home", "drive"];
  modes.forEach((m) => {
    const tabBtn = document.getElementById(`tab-${m}`);
    const viewEl = document.getElementById(`view-${m}`);
    if (tabBtn) tabBtn.classList.toggle("active", m === modeKey);
    if (viewEl) viewEl.classList.toggle("active", m === modeKey);
  });
}

// -----------------------------------------------------------------------------
// 2. Main Conversational Input & Quick Chips
// -----------------------------------------------------------------------------
function applyQuickPrompt(text) {
  const inputEl = document.getElementById("main-user-input");
  if (inputEl) {
    inputEl.value = text;
    handleMainInputSend();
  }
}

function simulateSpeechInput() {
  const micBtn = document.getElementById("btn-mic-trigger");
  if (micBtn) {
    micBtn.innerHTML = "🔴 <span>Listening...</span>";
    setTimeout(() => {
      micBtn.innerHTML = "🎙️ <span>Speak</span>";
      applyQuickPrompt("Actually make that Saturday morning");
    }, 1200);
  }
}

async function handleMainInputSend() {
  const inputEl = document.getElementById("main-user-input");
  if (!inputEl) return;
  const val = inputEl.value.trim();
  if (!val) return;

  // Process text through CHRONOS backend
  try {
    const res = await fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: val }),
    });
    const data = await res.json();
    console.log("CHRONOS response:", data);
  } catch (e) {
    console.error(e);
  }

  // Update Status Ribbon
  const reqRibbon = document.getElementById("ribbon-current-request");
  const planRibbon = document.getElementById("ribbon-current-plan");
  const liveStatus = document.getElementById("ribbon-live-status");

  if (val.toLowerCase().includes("saturday")) {
    triggerNaturalInterruption("Actually Saturday");
  } else if (val.toLowerCase().includes("chennai")) {
    triggerNaturalInterruption("Actually Chennai, not Mumbai");
  } else {
    if (reqRibbon) reqRibbon.innerText = val;
    if (planRibbon) planRibbon.innerText = "Search flights ➔ Compare prices ➔ Gated Booking";
    if (liveStatus) liveStatus.innerText = "✓ Active & Protected";
  }
}

// -----------------------------------------------------------------------------
// 3. Flagship Travel Mode: Natural Interruption & Stale Rejection
// -----------------------------------------------------------------------------
function triggerNaturalInterruption(correctionText) {
  const stream = document.getElementById("travel-messages-stream");
  const feedback = document.getElementById("interruption-feedback-text");
  const dateBadge = document.getElementById("flight-date-badge");
  const routeHeader = document.getElementById("flight-route-header");
  const ribbonReq = document.getElementById("ribbon-current-request");
  const ribbonStatus = document.getElementById("ribbon-live-status");

  if (correctionText.includes("Saturday")) {
    currentTravelDate = "Saturday, 11 Oct";
    if (dateBadge) dateBadge.innerText = "Saturday, 11 Oct";
    if (ribbonReq) ribbonReq.innerText = `${currentTravelDestination} · Saturday Morning · Cheapest Flight`;
    if (ribbonStatus) ribbonStatus.innerHTML = `Friday ➔ <span style="color: var(--brand-amber);">Updating</span> ➔ <span style="color: var(--brand-emerald);">Saturday ✓</span>`;

    // Append chat messages
    appendChatMessage(stream, "user", '"Actually Saturday."');
    setTimeout(() => {
      appendChatMessage(
        stream,
        "assistant",
        'Updated your request without restarting the whole task. I refreshed the flights for <strong>Saturday morning</strong>. Cheapest option is still Indigo 6E-204 at <strong>₹7,200</strong>.'
      );
    }, 400);

    if (feedback) {
      feedback.innerHTML = `<span style="color: var(--brand-emerald); font-weight: 700;">✓ Natural Interruption handled:</span> Updated date from Friday to Saturday while preserving search context.`;
    }

    // Call backend
    fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Actually Saturday morning" }),
    });

  } else if (correctionText.includes("Chennai")) {
    currentTravelDestination = "Delhi";
    if (routeHeader) routeHeader.innerText = "Chennai (MAA) ➔ Delhi (DEL)";
    if (ribbonReq) ribbonReq.innerText = `Delhi · ${currentTravelDate} · Cheapest Flight`;

    updateFlightCardRoutes("Delhi");

    appendChatMessage(stream, "user", '"Actually Chennai to Delhi, not Mumbai."');
    setTimeout(() => {
      appendChatMessage(
        stream,
        "assistant",
        'Destination updated to <strong>Delhi</strong>. Re-calculated 3 direct options for ' + currentTravelDate + '.'
      );
    }, 400);

    if (feedback) {
      feedback.innerHTML = `<span style="color: var(--brand-emerald); font-weight: 700;">✓ Destination Updated:</span> Replaced Mumbai query with Delhi with zero duplicate writes.`;
    }

    fetch("/api/user_input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "Actually Chennai to Delhi, not Mumbai" }),
    });
  }
}

function updateFlightCardRoutes(destination) {
  const r0 = document.getElementById("flight-card-route-0");
  const r1 = document.getElementById("flight-card-route-1");
  const r2 = document.getElementById("flight-card-route-2");
  if (r0) r0.innerText = `Indigo 6E-502 to ${destination}`;
  if (r1) r1.innerText = `Air India AI-801 to ${destination}`;
  if (r2) r2.innerText = `Vistara UK-920 to ${destination}`;
}

function appendChatMessage(container, role, htmlContent) {
  if (!container) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.innerHTML = htmlContent;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

// -----------------------------------------------------------------------------
// 4. Stale Result Rejection Demonstration
// -----------------------------------------------------------------------------
async function injectLateStaleResult() {
  const banner = document.getElementById("stale-notice-banner");
  if (banner) {
    banner.classList.add("visible");
  }

  const stream = document.getElementById("travel-messages-stream");
  appendChatMessage(
    stream,
    "assistant",
    `🛡️ <strong>Late Result Rejected:</strong> An older search result from your previous request arrived, but CHRONOS ignored it because your request had already changed.`
  );

  // Call backend to trigger stale rejection event
  await fetch("/api/inject_stale", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      call_id: "call_v1_delayed_delhi",
      origin_snapshot_id: "v1",
      tool_name: "search_flights",
      output: { flight: "OLD-DEL-888", price: 9500 },
    }),
  });
}

// -----------------------------------------------------------------------------
// 5. Interactive Flight Selection & Gated 4-Phase Booking
// -----------------------------------------------------------------------------
function selectFlight(index, price, time) {
  currentSelectedFlight = {
    index,
    price,
    time,
    route: `Chennai ➔ ${currentTravelDestination}`,
  };

  const cards = document.querySelectorAll(".flight-card-item");
  cards.forEach((c, idx) => c.classList.toggle("selected", idx === index));

  const descEl = document.getElementById("checkout-flight-desc");
  const priceEl = document.getElementById("checkout-price-val");
  const btnBookPrice = document.getElementById("btn-book-price");

  if (descEl) descEl.innerText = `${currentSelectedFlight.route} (${time} · ${currentTravelDate})`;
  if (priceEl) priceEl.innerText = price;
  if (btnBookPrice) btnBookPrice.innerText = price;
}

async function executeSafeBookingCommit() {
  const btn = document.getElementById("btn-confirm-booking");
  if (btn) {
    btn.innerHTML = "⏳ Validating Idempotency Gate...";
    btn.disabled = true;
  }

  // Call backend step_time to trigger commit controller
  await fetch("/api/step_time", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delta: 0.2 }),
  });

  setTimeout(() => {
    if (btn) {
      btn.innerHTML = "✓ Booking Committed Once (Protected by INV-3)";
      btn.style.background = "linear-gradient(135deg, #10b981, #059669)";
    }

    const stream = document.getElementById("travel-messages-stream");
    appendChatMessage(
      stream,
      "assistant",
      `🎉 <strong>Booking Confirmed!</strong> Your flight (${currentSelectedFlight.route} at ${currentSelectedFlight.time}) has been safely committed. Protected by current-state validation and strict idempotency.`
    );
  }, 500);
}

// -----------------------------------------------------------------------------
// 6. Mode 2: Smart Home / SmartThings Inspection & Correction
// -----------------------------------------------------------------------------
function correctHomeDiagnosis() {
  const box = document.getElementById("appliance-bounding-box");
  const label = document.getElementById("appliance-indicator-label");
  const code = document.getElementById("appliance-code-text");
  const stream = document.getElementById("home-messages-stream");
  const feedback = document.getElementById("home-feedback-msg");

  if (box) box.className = "detection-bounding-box power-corrected";
  if (label) label.innerText = "Power Status Indicator (Normal)";
  if (code) code.innerText = "Correction Applied: STATUS-OK";

  appendChatMessage(stream, "user", '"No, that\'s the power light."');
  setTimeout(() => {
    appendChatMessage(
      stream,
      "assistant",
      'Updated the diagnosis using your correction. The previous freezer diagnostic tool was cancelled, and the appliance status is marked as <strong>Healthy (Normal Power)</strong>.'
    );
  }, 400);

  if (feedback) {
    feedback.innerHTML = `<span style="color: var(--brand-emerald); font-weight: 700;">✓ Invalidation Applied:</span> Old freezer diagnostic cancelled. Power status verified.`;
  }
}

function resetHomeScenario() {
  const box = document.getElementById("appliance-bounding-box");
  const label = document.getElementById("appliance-indicator-label");
  const stream = document.getElementById("home-messages-stream");
  if (box) box.className = "detection-bounding-box";
  if (label) label.innerText = "Freezer Warning Indicator";
  if (stream) {
    stream.innerHTML = `
      <div class="chat-bubble assistant">
        "I analyzed the camera frame and detected a <strong>freezer warning light</strong>. Scheduling diagnostic tool..."
      </div>
    `;
  }
}

// -----------------------------------------------------------------------------
// 7. Mode 3: Drive / Cockpit GPS Rerouting
// -----------------------------------------------------------------------------
function rerouteDriveCockpit() {
  const routePath = document.getElementById("active-route-path");
  const routeName = document.getElementById("drive-route-name");
  const etaVal = document.getElementById("drive-eta-val");
  const stream = document.getElementById("drive-messages-stream");
  const feedback = document.getElementById("drive-feedback-msg");

  if (routePath) {
    routePath.setAttribute("d", "M 30 180 Q 200 230 400 60");
    routePath.setAttribute("stroke", "var(--brand-emerald)");
  }
  if (routeName) routeName.innerText = "Scenic Old Road (Detour)";
  if (etaVal) etaVal.innerText = "48 min";

  appendChatMessage(stream, "user", '"Don\'t take the highway. Use the old road."');
  setTimeout(() => {
    appendChatMessage(
      stream,
      "assistant",
      'Route updated without continuing the outdated instruction. Highway 10 guidance cancelled, switched to <strong>Scenic Old Road</strong>.'
    );
  }, 400);

  if (feedback) {
    feedback.innerHTML = `<span style="color: var(--brand-emerald); font-weight: 700;">✓ Reroute Successful:</span> Outdated navigation node purged from active execution tree.`;
  }
}

function resetDriveScenario() {
  const routePath = document.getElementById("active-route-path");
  const routeName = document.getElementById("drive-route-name");
  const etaVal = document.getElementById("drive-eta-val");
  const stream = document.getElementById("drive-messages-stream");

  if (routePath) {
    routePath.setAttribute("d", "M 30 180 Q 150 40 400 60");
    routePath.setAttribute("stroke", "var(--brand-cyan)");
  }
  if (routeName) routeName.innerText = "Highway 10 Express";
  if (etaVal) etaVal.innerText = "42 min";
  if (stream) {
    stream.innerHTML = `
      <div class="chat-bubble assistant">
        "Navigating to Airport via <strong>Highway 10</strong>. Estimated arrival at 09:22 AM."
      </div>
    `;
  }
}

// -----------------------------------------------------------------------------
// 8. Advanced Inspector Drawer & Live SSE Stream
// -----------------------------------------------------------------------------
function toggleInspectorDrawer() {
  const drawer = document.getElementById("inspector-drawer-panel");
  if (drawer) drawer.classList.toggle("open");
}

function initSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/events/stream");

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event) appendRawTelemetry(data.event);
    } catch (e) {
      console.error("SSE parse error", e);
    }
  };

  eventSource.onerror = () => {
    setTimeout(initSSE, 3000);
  };
}

function appendRawTelemetry(evt) {
  const container = document.getElementById("raw-telemetry-feed");
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
  entry.style.borderLeft = `2px solid ${col}`;
  entry.style.padding = "2px 6px";
  entry.innerHTML = `
    <span style="color: ${col}; font-weight: bold;">[${evt.event_type}]</span>
    <span style="color: #64748b;">@${evt.timestamp.toFixed(2)}s (${evt.snapshot_id || "v0"})</span>:
    <span>${JSON.stringify(evt.payload || {})}</span>
  `;
  container.prepend(entry);
}

// -----------------------------------------------------------------------------
// Initialize on DOM Ready
// -----------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  initSSE();
});
