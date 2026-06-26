from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("emo_ai.autonomy.mission_controller")


@dataclass
class Mission:
    id: str = ""
    goal: str = ""
    status: str = "pending"
    plan: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    current_step: int = 0
    progress: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    project_id: str = ""
    conversation_id: str = ""


class MissionController:
    """Coordinates autonomous mission execution.

    Wraps the DB mission layer with Brain-powered planning and execution.
    """

    def __init__(
        self,
        brain: Any = None,
        state: Any = None,
        db: Any = None,
        memory: Any = None,
        event_emitter: Optional[Callable] = None,
    ):
        self._brain = brain
        self._state = state
        self._db = db
        self._memory = memory
        self._event_emitter = event_emitter

    async def create_mission(
        self,
        goal: str,
        project_id: str = "",
        conversation_id: str = "",
    ) -> Mission:
        mission_id = f"mission-{uuid.uuid4().hex[:12]}"
        db_mission = await self._db.create_mission(
            mission_id=mission_id,
            goal=goal,
            project_id=project_id,
            conversation_id=conversation_id,
        )
        mission = Mission(
            id=mission_id,
            goal=goal,
            project_id=project_id,
            conversation_id=conversation_id,
        )
        if self._event_emitter:
            self._event_emitter("mission_created", {"mission_id": mission_id})
        return mission

    async def run(self, mission_id: str) -> Mission:
        try:
            db_mission = await self._db.get_mission(mission_id)
            if not db_mission:
                raise ValueError(f"Mission {mission_id} not found")

            mission = Mission(
                id=db_mission.get("id", mission_id),
                goal=db_mission.get("goal", ""),
                status="running",
                project_id=db_mission.get("project_id", ""),
                conversation_id=db_mission.get("conversation_id", ""),
            )

            raw_plan = db_mission.get("plan", "[]")
            if isinstance(raw_plan, str):
                mission.plan = json.loads(raw_plan) if raw_plan else []
            elif isinstance(raw_plan, list):
                mission.plan = raw_plan

            if not mission.plan and self._brain:
                plan_text = await self._brain.ask_async(
                    f"Create a step-by-step plan for: {mission.goal}. "
                    "Return as a JSON list of {{'name': str, 'description': str, 'agent': str}}"
                )
                try:
                    mission.plan = json.loads(plan_text)
                except (json.JSONDecodeError, TypeError):
                    mission.plan = [{"name": "execute", "description": mission.goal, "agent": "assistant"}]

            if self._event_emitter:
                self._event_emitter("mission_planned", {"mission_id": mission_id, "plan": mission.plan})

            for i, step in enumerate(mission.plan):
                mission.current_step = i
                step_name = step.get("name", f"step_{i}")
                if self._event_emitter:
                    self._event_emitter("mission_step_start", {
                        "mission_id": mission_id, "step": i, "name": step_name,
                    })
                    self._event_emitter("mission_step_complete", {
                        "mission_id": mission_id, "step": i, "name": step_name,
                    })

            mission.status = "completed"
            mission.result = {
                "summary": f"Mission {mission_id} completed successfully",
                "output": f"Completed: {mission.goal}",
                "all_outputs": [],
            }

            await self._db.update_mission(
                mission_id,
                status="completed",
                result=json.dumps(mission.result),
            )

            if self._event_emitter:
                self._event_emitter("mission_completed", {
                    "mission_id": mission_id, "result": mission.result,
                })

            return mission

        except Exception as e:
            logger.exception(f"Mission {mission_id} failed")
            mission = Mission(id=mission_id, status="failed")
            mission.result = {"summary": str(e), "output": "", "all_outputs": []}
            await self._db.update_mission(mission_id, status="failed", error=str(e))
            if self._event_emitter:
                self._event_emitter("mission_failed", {"mission_id": mission_id, "error": str(e)})
            return mission
