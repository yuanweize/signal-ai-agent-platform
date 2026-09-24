"""
Tests for Skill Disabling and Fallback semantics.
Verifies Section 13:
- Disabling customer-support prevents it from being selected in graph
- SkillRegistry.load_body() returns empty string for disabled skill
- When disabled, customer-support is not selected by AgentRuntime and not in AIRun.skills
- Persistence across sync_persisted_states
"""

import json

import pytest
from sqlalchemy import select

from app.ai.runtime.agent_runtime import AgentRuntime
from app.ai.runtime.context import AgentContext
from app.ai.skills.registry import skill_registry
from app.models.ai import AIRun
from app.models.conversation import Conversation, ConversationType


def test_skill_registry_load_body_blocks_disabled_skill():
    """SkillRegistry.load_body must not return body of disabled skill."""
    skill = skill_registry.get("customer-support")
    assert skill is not None

    try:
        # Enabled returns content
        skill_registry.set_enabled("customer-support", True)
        body = skill_registry.load_body("customer-support")
        assert len(body) > 0

        # Disable skill
        skill_registry.set_enabled("customer-support", False)
        assert skill_registry.get("customer-support").is_enabled is False

        # Disabled returns empty string
        disabled_body = skill_registry.load_body("customer-support")
        assert disabled_body == ""
    finally:
        skill_registry.set_enabled("customer-support", True)


@pytest.mark.asyncio
async def test_agent_runtime_does_not_load_disabled_customer_support(session):
    """AgentRuntime must not select customer-support when it is disabled."""
    conv = Conversation(type=ConversationType.dm.value, signal_id="+100", mode="auto")
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    try:
        skill_registry.set_enabled("customer-support", False)

        runtime = AgentRuntime(is_test=True)
        ctx = AgentContext(
            conversation_id=conv.id,
            sender_id="+100",
            text="Hello, how can you help me today?",
            mode="auto",
        )
        res = await runtime.run(session, ctx)

        run = (await session.execute(select(AIRun).where(AIRun.id == res.ai_run_id))).scalar_one()
        selected_skills = json.loads(run.skills) if run.skills else []
        assert "customer-support" not in selected_skills
    finally:
        skill_registry.set_enabled("customer-support", True)
        await session.delete(conv)
        await session.commit()


@pytest.mark.asyncio
async def test_disabled_skill_state_persists_across_sync(session):
    """Disabled skill state in DB persists and is respected after sync_persisted_states."""
    from app.models.config import BotConfig

    db_state = BotConfig(
        key="skill_enabled:customer-support",
        value="false",
        category="skills",
    )
    session.add(db_state)
    await session.commit()

    try:
        skill_registry.set_enabled("customer-support", True)
        assert skill_registry.get("customer-support").is_enabled is True

        await skill_registry.sync_persisted_states(session)
        assert skill_registry.get("customer-support").is_enabled is False
        assert skill_registry.load_body("customer-support") == ""
    finally:
        skill_registry.set_enabled("customer-support", True)
        await session.delete(db_state)
        await session.commit()
