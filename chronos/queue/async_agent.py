"""
CHRONOS Dual-Queue Asynchronous Agent
Implements the Participant Objectives & Interface Contract (Section 3 of Theme 05 Evaluation Specification).
Communicates over two asynchronous queues: input events queue and output actions queue.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
import uuid

from chronos.protocol.events import Event, EventType, InterruptionLevel
from chronos.protocol.schemas import CallStatus, ExecutionClass, ToolCall, ToolResult, ToolDefinition
from chronos.protocol.messages import UserMessage, FastAckSignal, AgentResponse
from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.queue.schemas import (
    InputEvent,
    InputEventType,
    OutputAction,
    OutputActionType,
    TranscribedTextChunk,
    RawAudioClip,
    VideoFrame,
    InterruptionSignal,
    ToolResultEvent,
    ScenarioToolManifest,
    SpokenFillerAction,
    ToolCallAction,
    ToolCancelAction,
    ClarificationRequestAction,
    FinalResponseAction,
)
from chronos.perception.grounding import VisualScene, VisualObject, MultimodalGrounder

logger = logging.getLogger("chronos.queue.async_agent")


class DualQueueAgent:
    """
    Asynchronous Actor communicating exclusively via two queues:
      - input_queue: asyncio.Queue[InputEvent]
      - output_queue: asyncio.Queue[OutputAction]
    """

    def __init__(
        self,
        input_queue: Optional[asyncio.Queue[InputEvent]] = None,
        output_queue: Optional[asyncio.Queue[OutputAction]] = None,
        clock: Optional[VirtualClock] = None,
    ):
        self.clock = clock or VirtualClock(initial_time=0.0, mode="stepped")
        self.agent = ChronosAgent(clock=self.clock)
        self.input_queue: asyncio.Queue[InputEvent] = input_queue or asyncio.Queue()
        self.output_queue: asyncio.Queue[OutputAction] = output_queue or asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._action_trace: List[OutputAction] = []
        self._input_trace: List[InputEvent] = []

    @property
    def action_trace(self) -> List[OutputAction]:
        return list(self._action_trace)

    @property
    def input_trace(self) -> List[InputEvent]:
        return list(self._input_trace)

    async def emit_action(self, action: OutputAction) -> None:
        """Pushes action into the output queue and records in trace."""
        self._action_trace.append(action)
        await self.output_queue.put(action)

    async def start(self) -> None:
        """Starts the asynchronous consumer loop."""
        self._running = True
        self._worker_task = asyncio.create_task(self._event_loop())

    async def stop(self) -> None:
        """Stops the consumer loop."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def step(self) -> Optional[InputEvent]:
        """Process a single event from the input queue synchronously or during stepping."""
        if self.input_queue.empty():
            return None
        event = await self.input_queue.get()
        await self._process_input_event(event)
        return event

    async def _event_loop(self) -> None:
        """Main asynchronous event processing loop."""
        while self._running:
            try:
                event = await self.input_queue.get()
                await self._process_input_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing queue event: {e}", exc_info=True)

    async def _process_input_event(self, event: InputEvent) -> None:
        self._input_trace.append(event)
        now = event.timestamp
        self.clock.advance_to(now)

        if isinstance(event, TranscribedTextChunk):
            await self._handle_transcribed_text(event)
        elif isinstance(event, RawAudioClip):
            await self._handle_raw_audio(event)
        elif isinstance(event, VideoFrame):
            await self._handle_video_frame(event)
        elif isinstance(event, InterruptionSignal):
            await self._handle_interruption_signal(event)
        elif isinstance(event, ToolResultEvent):
            await self._handle_tool_result(event)
        elif isinstance(event, ScenarioToolManifest):
            await self._handle_tool_manifest(event)

    async def _handle_transcribed_text(self, event: TranscribedTextChunk) -> None:
        text = event.text.strip()
        cur_snap = self.agent.state_mgr.get_current_snapshot()
        
        # 1. Floor management: Emit Fast Acknowledgment / Spoken Filler immediately
        fast_ack = self.agent.floor_controller.generate_fast_ack(
            level=InterruptionLevel.LEVEL_1 if cur_snap.snapshot_id != "v0" else InterruptionLevel.LEVEL_0,
            snapshot_id=cur_snap.snapshot_id,
            slot_updates={},
        )
        if fast_ack and fast_ack.ack_text:
            await self.emit_action(
                SpokenFillerAction(
                    text=fast_ack.ack_text,
                    filler_type="fast_ack",
                    snapshot_id=cur_snap.snapshot_id,
                    timestamp=self.clock.now(),
                )
            )

        # 2. Check for ambiguity or speech hesitations
        if "wait" in text.lower() and "actually" not in text.lower():
            # Speech hesitation marker without resolution -> clarify
            await self.emit_action(
                ClarificationRequestAction(
                    question="Take your time, let me know how you'd like to adjust that.",
                    ambiguous_slots=["user_intent"],
                    snapshot_id=cur_snap.snapshot_id,
                    timestamp=self.clock.now(),
                )
            )
            return

        # 3. Process user input through CHRONOS temporal control plane
        res = self.agent.process_user_input(text)
        new_snap_id = res.get("snapshot_id", cur_snap.snapshot_id)

        # 4. Check for newly cancelled calls and emit ToolCancelAction
        if res.get("interruption"):
            cancelled_ids = res["interruption"].get("cancelled_calls", [])
            for c_id in cancelled_ids:
                await self.emit_action(
                    ToolCancelAction(
                        call_id=c_id,
                        reason=f"superseded_by_{new_snap_id}",
                        snapshot_id=new_snap_id,
                        timestamp=self.clock.now(),
                    )
                )

        # 5. Check for newly dispatched tool calls and emit ToolCallAction
        active_calls = self.agent.scheduler.get_active_calls()
        for call in active_calls:
            if call.snapshot_id == new_snap_id and call.status.value in ("DISPATCHED", "RUNNING"):
                tool_def = self.agent.registry.get(call.tool_name)
                is_mod = (tool_def.execution_class == ExecutionClass.IRREVERSIBLE_WRITE) if tool_def else False
                await self.emit_action(
                    ToolCallAction(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        arguments=call.arguments,
                        snapshot_id=call.snapshot_id,
                        is_state_modifying=is_mod,
                        idempotency_key=call.idempotency_key,
                        timestamp=self.clock.now(),
                    )
                )

        # 6. Check if final response / confirmation was produced
        final_resp = self.agent.get_last_response()
        if final_resp:
            snap = self.agent.state_mgr.get_current_snapshot()
            await self.emit_action(
                FinalResponseAction(
                    text=final_resp.text,
                    snapshot_id=snap.snapshot_id,
                    intent=snap.intent_name,
                    slots=snap.slots,
                    state_snapshot=snap.model_dump(),
                    timestamp=self.clock.now(),
                )
            )

    async def _handle_raw_audio(self, event: RawAudioClip) -> None:
        """Processes audio input clip with conversational acknowledgment."""
        cur_snap = self.agent.state_mgr.get_current_snapshot()
        
        # Audio conversational acknowledgment
        await self.emit_action(
            SpokenFillerAction(
                text="Listening...",
                filler_type="fast_ack",
                snapshot_id=cur_snap.snapshot_id,
                timestamp=self.clock.now(),
            )
        )

        transcription = event.transcription or ""
        if transcription:
            text_chunk = TranscribedTextChunk(
                text=transcription,
                end_of_turn=True,
                confidence=1.0,
                timestamp=event.timestamp + 0.05,
            )
            await self._handle_transcribed_text(text_chunk)

    async def _handle_video_frame(self, event: VideoFrame) -> None:
        """Processes visual frame and performs multimodal intent grounding."""
        cur_snap = self.agent.state_mgr.get_current_snapshot()
        
        scene = VisualScene(
            scene_id=f"scene_{uuid.uuid4().hex[:6]}",
            timestamp=event.timestamp,
            detected_objects=[
                VisualObject(
                    object_id=obj.get("object_id", f"obj_{i}"),
                    label=obj.get("label", "unknown"),
                    attributes=obj.get("attributes", {}),
                    confidence=obj.get("confidence", 1.0),
                )
                for i, obj in enumerate(event.detected_objects)
            ],
            raw_metadata=event.raw_metadata,
        )

        updated_slots = self.agent.grounder.resolve_multimodal_correction(
            scene=scene,
            user_utterance="check frame",
            current_slots=cur_snap.slots,
        )

        if updated_slots != cur_snap.slots:
            new_snap = self.agent.state_mgr.create_snapshot(
                intent_name=cur_snap.intent_name or "device_troubleshooting",
                slots=updated_slots,
                timestamp=self.clock.now(),
            )
            await self.emit_action(
                SpokenFillerAction(
                    text="Inspecting camera frame...",
                    filler_type="progress_narration",
                    snapshot_id=new_snap.snapshot_id,
                    timestamp=self.clock.now(),
                )
            )

    async def _handle_interruption_signal(self, event: InterruptionSignal) -> None:
        """Handles user barge-in / explicit interruption signal."""
        cur_snap = self.agent.state_mgr.get_current_snapshot()
        ir = self.agent.interruption_controller.handle_interruption(
            text=event.reason or "stop"
        )
        for c_id in ir.cancelled_call_ids:
            await self.emit_action(
                ToolCancelAction(
                    call_id=c_id,
                    reason=f"interruption_{event.reason}",
                    snapshot_id=cur_snap.snapshot_id,
                    timestamp=self.clock.now(),
                )
            )

    async def _handle_tool_result(self, event: ToolResultEvent) -> None:
        """Ingests asynchronous tool execution result."""
        stale_res = self.agent.force_inject_stale_result(
            call_id=event.call_id,
            origin_snapshot_id=event.snapshot_id,
            tool_name=event.tool_name,
            output=event.output,
        )
        
        snap = self.agent.state_mgr.get_current_snapshot()
        if stale_res.status == CallStatus.COMPLETED:
            resp_text = f"Received results for {event.tool_name}. Ready to proceed."
            await self.emit_action(
                FinalResponseAction(
                    text=resp_text,
                    snapshot_id=snap.snapshot_id,
                    intent=snap.intent_name,
                    slots=snap.slots,
                    state_snapshot=snap.model_dump(),
                    timestamp=self.clock.now(),
                )
            )

    async def _handle_tool_manifest(self, event: ScenarioToolManifest) -> None:
        """Dynamically registers tools from manifest at runtime."""
        for tool_dict in event.tools:
            t_def = ToolDefinition(**tool_dict)
            self.agent.registry.register(t_def)
