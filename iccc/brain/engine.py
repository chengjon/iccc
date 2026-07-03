"""
Brain Engine.
The cognitive core of the system, responsible for the Spec-Driven Development cycle.
"""

import logging
from pathlib import Path
from typing import Optional

from iccc.agents.client import ClaudeClient
from iccc.brain.prompts import (
    ANALYZE_REQUIREMENTS_PROMPT,
    BRAIN_SYSTEM_PROMPT,
    GENERATE_PLAN_PROMPT,
)
from iccc.core.specs import SpecManager
from iccc.models.entities import Message, ModelTier
from iccc.parsers.markdown_parser import MarkdownTaskParser

logger = logging.getLogger(__name__)


class BrainEngine:
    """
    The Brain Engine orchestrates the cognitive process:
    Think -> Spec -> Plan
    """

    def __init__(self, project_root: Path, client: Optional[ClaudeClient] = None):
        self.project_root = project_root
        self.specs = SpecManager(project_root)
        self.client = client or ClaudeClient()  # Expects env vars for API key

    async def run_cycle(self, user_request: str = "") -> None:
        """
        Run a full cognitive cycle.
        1. Analyze inputs -> Update IDEAS.md
        2. Enforce rules -> Update INSTITUTION.md (Optional/On-demand)
        3. Create Plan -> Update MAINTASK.md
        """
        logger.info("Brain: Starting cognitive cycle...")

        # 1. Update IDEAS.md
        await self._update_ideas(user_request)

        # 2. Update INSTITUTION.md (Skipped for now, usually static or explicit update)
        # await self._update_institution()

        # 3. Update MAINTASK.md
        await self._update_maintask()

        logger.info("Brain: Cycle complete.")

    async def _update_ideas(self, user_request: str) -> None:
        """Analyze requirements and update IDEAS.md"""
        logger.info("Brain: Analyzing requirements...")
        
        current_ideas = self.specs.load_ideas()
        
        # Prepare context for Claude
        prompt = ANALYZE_REQUIREMENTS_PROMPT.format(
            input_summary=user_request or "No new direct user input. Review current state.",
            current_ideas=current_ideas.content
        )
        
        messages = [Message(role="user", content=prompt)]
        
        # Brain uses Opus for deep thinking
        response = await self.client.send_message(
            messages=messages,
            model=ModelTier.OPUS, 
            system=BRAIN_SYSTEM_PROMPT
        )
        
        new_content = response["content"]
        self.specs.save_ideas(new_content)
        logger.info("Brain: IDEAS.md updated.")

    async def _update_maintask(self) -> None:
        """Generate tasks based on ideas and rules."""
        logger.info("Brain: Generating plan...")
        
        ideas = self.specs.load_ideas()
        institution = self.specs.load_institution()
        current_maintask = self.specs.load_maintask()
        
        prompt = GENERATE_PLAN_PROMPT.format(
            ideas_content=ideas.content,
            institution_content=institution.content,
            current_maintask=current_maintask.content
        )
        
        messages = [Message(role="user", content=prompt)]
        
        response = await self.client.send_message(
            messages=messages,
            model=ModelTier.OPUS,
            system=BRAIN_SYSTEM_PROMPT
        )
        
        new_content = response["content"]
        self.specs.save_maintask(new_content)
        
        # Parse and save structured tasks for execution
        try:
            tasks_data = MarkdownTaskParser.parse(new_content)
            import json
            tasks_json_path = self.project_root / ".iccc" / ".plans" / "current_tasks.json"
            tasks_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tasks_json_path, "w") as f:
                json.dump(tasks_data, f, indent=2)
            logger.info(f"Brain: Parsed {len(tasks_data)} tasks to {tasks_json_path}")
        except Exception as e:
            logger.error(f"Failed to parse tasks from MAINTASK.md: {e}")

        logger.info("Brain: MAINTASK.md updated.")
