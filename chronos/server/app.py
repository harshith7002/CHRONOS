"""
CHRONOS FastAPI Server
Provides REST endpoints and Server-Sent Events (SSE) for the real-time control plane UI.
"""

from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.evaluation.harness import ReplayHarness
from chronos.evaluation.metrics import MetricsCollector
from chronos.evaluation.benchmarks import LatencyBenchmark

app = FastAPI(title="CHRONOS Temporal Control Plane", version="1.0.0")

# Shared global agent instance
clock = VirtualClock(initial_time=0.0, mode="realtime", time_scale=1.0)
agent = ChronosAgent(clock=clock)
replay_harness = ReplayHarness(agent=agent)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class UserInputRequest(BaseModel):
    text: str


class TimeStepRequest(BaseModel):
    delta: float = 0.1


class StaleInjectRequest(BaseModel):
    call_id: str = "call_delhi_old"
    origin_snapshot_id: str = "v1"
    tool_name: str = "search_flights"
    output: Dict[str, Any] = {"flight_id": "DEL-999", "price": 5000, "dest": "Delhi"}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>CHRONOS Control Plane UI</h1>")


@app.get("/api/state")
async def get_state():
    return agent.get_state_summary()


@app.post("/api/user_input")
async def send_user_input(req: UserInputRequest):
    res = agent.process_user_input(req.text)
    return {"status": "ok", "result": res, "state": agent.get_state_summary()}


@app.post("/api/step_time")
async def step_time(req: TimeStepRequest):
    results = agent.step_time(req.delta)
    return {"status": "ok", "new_time": agent.clock.now(), "state": agent.get_state_summary()}


@app.post("/api/inject_stale")
async def inject_stale(req: StaleInjectRequest):
    result = agent.force_inject_stale_result(
        call_id=req.call_id,
        origin_snapshot_id=req.origin_snapshot_id,
        tool_name=req.tool_name,
        output=req.output,
    )
    return {"status": "ok", "result": result.model_dump(), "state": agent.get_state_summary()}


@app.post("/api/run_demo")
async def run_demo():
    report = replay_harness.run_default_demo_scenario()
    return {"status": "ok", "report": report.model_dump(), "state": agent.get_state_summary()}


@app.post("/api/run_chained")
async def run_chained():
    res = replay_harness.run_chained_dag_invalidation_scenario()
    return {"status": "ok", "result": res, "state": agent.get_state_summary()}


@app.post("/api/run_adversarial")
async def run_adversarial():
    res = replay_harness.run_adversarial_stale_booking_injection_scenario()
    return {"status": "ok", "result": res, "state": agent.get_state_summary()}


@app.post("/api/run_multimodal")
async def run_multimodal():
    res = replay_harness.run_multimodal_vision_correction_scenario()
    return {"status": "ok", "result": res, "state": agent.get_state_summary()}


@app.post("/api/run_matrix")
async def run_matrix():
    from chronos.evaluation.adversarial_matrix import AdversarialBenchmarkRunner
    summary = AdversarialBenchmarkRunner.run_matrix(seeds_per_scenario=25)
    return {"status": "ok", "summary": summary.model_dump()}


@app.post("/api/canonical_scenarios")
async def run_canonical_scenarios():
    from chronos.evaluation.canonical_scenarios import CanonicalScenarioRunner
    report = await CanonicalScenarioRunner.run_all_9_canonical_scenarios()
    return {"status": "ok", "report": report.model_dump()}


@app.get("/api/scoring_rubric")
async def get_scoring_rubric():
    return {
        "theme": "Theme 05: Interruptible Real-Time Agents",
        "scoring_weights": {
            "task_completion": {"weight": "40%", "criteria": "Correct tool execution, valid argument extraction, state snapshot accuracy, proper final response grounding."},
            "interruption_recovery": {"weight": "35%", "criteria": "Prompt cancellation of invalidated calls, absence of stale re-runs, updated state snapshots."},
            "response_latency": {"weight": "15%", "criteria": "Time to first substantive spoken action following user input or interruption (<200ms)."},
            "safety_and_protocol": {"weight": "10%", "criteria": "Zero duplicate state-changing calls, structured schema adherence, valid state payloads."}
        },
        "multipliers": {
            "quality_multiplier": "0.80x - 1.20x (evaluates transcript naturalness, truthfulness, relevance)",
            "multimodal_multiplier": "1.50x for multimodal audio/video scenarios"
        },
        "execution_constraints": {
            "runtime": "Python 3.10 - 3.13",
            "state_scope": "Session-scoped memory only (no cross-session caching)",
            "wall_clock_cap": "120s per scenario"
        }
    }


@app.post("/api/run_benchmark")
async def run_benchmark():
    report = LatencyBenchmark.run_full_benchmark(iterations=500)
    return {"status": "ok", "benchmark": report.model_dump()}


@app.post("/api/reset")
async def reset():
    agent.reset()
    return {"status": "ok", "state": agent.get_state_summary()}


@app.get("/api/events/stream")
async def event_stream(request: Request):
    """Server-Sent Events stream for real-time telemetry updates."""
    async def sse_generator():
        q: asyncio.Queue = asyncio.Queue()

        def listener(evt):
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(q.put_nowait, evt)
            except Exception:
                pass

        agent.event_log.subscribe(listener)
        try:
            init_payload = json.dumps({"type": "INIT", "state": agent.get_state_summary()})
            yield f"data: {init_payload}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=1.0)
                    msg = json.dumps({
                        "type": "EVENT",
                        "event": evt.model_dump(),
                        "state": agent.get_state_summary(),
                    })
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    hb = json.dumps({"type": "HEARTBEAT", "state": agent.get_state_summary()})
                    yield f"data: {hb}\n\n"
        finally:
            agent.event_log.unsubscribe(listener)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
