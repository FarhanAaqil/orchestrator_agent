"""
orchestrator_core/runner/context.py

Reconstructs execution context and conversation history from SQLite checkpoints
(JobRecord and JobStepRecord list) to guarantee deterministic crash-resumption (Section 5.3 & 5.5).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from orchestrator_core.models import JobRecord, JobStepRecord


_DEFAULT_SYSTEM_TEMPLATE = """You are an autonomous agent in Farhan Aaqil's personal orchestrator system.
Your agent name: {agent}
Job ID: {job_id}
Thread ID: {thread_id}

You operate in a structured ReAct loop. In each turn, you evaluate the goal, parameters, and prior step observations, then output a JSON object specifying your next action.

Output JSON format (must be valid JSON, nothing else):
{{
  "thought": "Analytical reasoning about the current state, findings, and what must be done next",
  "action": "tool_call" | "propose" | "handoff" | "ask_user" | "final",
  "action_input": {{ ... }}
}}

Action specifications:
1. "tool_call": Execute an internal tool, search, or research sub-routine.
   action_input: {{"name": "<tool_name>", "args": {{ ... }}}}

2. "propose": Queue an external side-effect (e.g. sending email, publishing blog post, social media post) for human review and approval.
   action_input: {{
     "action_type": "send_email" | "publish_hashnode" | "publish_devto" | "linkedin_post" | "github_issue",
     "payload": {{ ... }},
     "target": "<recipient or target platform>"
   }}

3. "handoff": Delegate a sub-task to another specialized agent.
   action_input: {{
     "target_agent": "<agent_name>",
     "sub_goal": "<detailed task description for child agent>",
     "params": {{ ... }}
   }}

4. "ask_user": Pause and request clarification, missing input, or confirmation from the user.
   action_input: {{
     "question": "<clear, concise question>"
   }}

5. "final": You have satisfied the job goal. Provide the final completed output.
   action_input: {{
     "summary": "<comprehensive result or artifact summary>"
   }}
"""


def build_system_prompt(job: JobRecord, custom_instructions: Optional[str] = None) -> str:
    """Build the system prompt for the agent runner."""
    base = _DEFAULT_SYSTEM_TEMPLATE.format(
        agent=job.agent,
        job_id=job.id,
        thread_id=job.thread_id,
    )
    if custom_instructions:
        base += f"\nSpecial Agent Instructions:\n{custom_instructions}\n"
    return base


def build_messages(
    job: JobRecord,
    steps: list[JobStepRecord],
    custom_instructions: Optional[str] = None,
) -> list[dict[str, str]]:
    """
    Rebuild the full message history from persisted steps in SQLite.
    Guarantees deterministic resumption after process crashes or worker restarts.
    """
    messages: list[dict[str, str]] = []

    # 1. System prompt
    system_prompt = build_system_prompt(job, custom_instructions)
    messages.append({"role": "system", "content": system_prompt})

    # 2. Initial user goal
    goal_content = f"Goal: {job.goal}\nParameters: {job.params_json}"
    messages.append({"role": "user", "content": goal_content})

    # 3. Chronological replay of prior steps
    for step in sorted(steps, key=lambda s: s.idx):
        if step.kind == "llm":
            messages.append({"role": "assistant", "content": step.output_json or ""})
        elif step.kind == "tool":
            messages.append({
                "role": "user",
                "content": f"Observation from {step.name or 'tool'}:\n{step.output_json or ''}",
            })
        elif step.kind == "propose":
            messages.append({
                "role": "user",
                "content": f"System: Proposal for {step.name or 'action'} queued for human approval. Output: {step.output_json or ''}",
            })
        elif step.kind == "note":
            if step.name == "user_answer":
                messages.append({
                    "role": "user",
                    "content": f"User answer: {step.output_json or ''}",
                })
            elif step.name == "loop_warning":
                messages.append({
                    "role": "user",
                    "content": f"System Warning: {step.output_json or ''}",
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"System Note [{step.name}]: {step.output_json or ''}",
                })
        elif step.kind == "error":
            messages.append({
                "role": "user",
                "content": f"Error in step {step.idx} ({step.name}): {step.output_json or ''}",
            })

    return messages
