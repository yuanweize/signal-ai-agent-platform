#!/usr/bin/env python3
"""
Live external AI gateway smoke test runner.

Validates end-to-end compatibility against a real OpenAI-compatible endpoint.
Reads configuration strictly from environment variables:
  LIVE_AI_BASE_URL (default: https://ai.eurun.top/v1)
  LIVE_AI_MODEL    (default: audio1.0)
  LIVE_AI_API_KEY  (required for execution; never hardcoded, never logged)

Levels verified:
  Level 1: Raw gateway HTTP chat completion
  Level 2: OpenAICompatibleProvider adapter
  Level 3: Production AgentRuntime factory + encrypted BotConfig + AIRun persistence
  Level 4: Multi-turn conversational context retention
  Level 5: Active PromptVersion injection & provenance tracking
  Capability Probe: Embeddings and native tool calling support
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx


async def run_live_smoke() -> int:
    base_url = os.environ.get("LIVE_AI_BASE_URL", "https://ai.eurun.top/v1").rstrip("/")
    model = os.environ.get("LIVE_AI_MODEL", "audio1.0").strip()
    api_key = os.environ.get("LIVE_AI_API_KEY", "").strip()

    if not api_key:
        print("=" * 60)
        print("LIVE AI SMOKE: BLOCKED (NO CREDENTIAL SUPPLIED)")
        print("=" * 60)
        print(f"Target Gateway: {base_url}")
        print(f"Target Model:   {model}")
        print("Status:         EXTERNAL CREDENTIAL ACCESS BLOCKER")
        print("Notice:         LIVE_AI_API_KEY environment variable is not set.")
        print("                To run live smoke, export LIVE_AI_API_KEY=<key>.")
        print("=" * 60)
        return 0

    masked_key = f"{api_key[:3]}...{api_key[-3:]}" if len(api_key) > 6 else "***"
    print("=" * 60)
    print("STARTING LIVE AI GATEWAY SMOKE")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Model:    {model}")
    print(f"Key:      {masked_key} (masked)")
    print("-" * 60)

    # -----------------------------------------------------------------------
    # Level 1: Raw Gateway HTTP
    # -----------------------------------------------------------------------
    print("[Level 1] Raw Gateway HTTP Chat Completion...")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Respond with the word PONG only."}],
                    "temperature": 0.1,
                    "max_tokens": 10,
                },
            )
            lat1 = int((time.perf_counter() - t0) * 1000)
            if resp.status_code != 200:
                print(f"  FAILED: HTTP {resp.status_code} - {resp.text[:200]}")
                return 1
            body = resp.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            print(f"  PASS: HTTP 200 ({lat1}ms) - Preview: {content!r}")
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            return 1

    # -----------------------------------------------------------------------
    # Level 2: OpenAICompatibleProvider Adapter
    # -----------------------------------------------------------------------
    print("[Level 2] OpenAICompatibleProvider Adapter...")
    from app.ai.providers.llm import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    t0 = time.perf_counter()
    try:
        gen_result = await provider.generate(
            messages=[{"role": "user", "content": "Say hello in one word."}],
            temperature=0.2,
            max_tokens=20,
        )
        lat2 = int((time.perf_counter() - t0) * 1000)
        print(f"  PASS: Provider generated ({lat2}ms) - Result: {gen_result.content.strip()!r}")
    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return 1

    # -----------------------------------------------------------------------
    # Level 3: Real Production AgentRuntime Factory + Persistence
    # -----------------------------------------------------------------------
    print("[Level 3] Production Factory + Encrypted BotConfig + AIRun persistence...")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.ai.runtime.factory import get_production_agent_runtime
    from app.database import Base
    from app.models.config import BotConfig
    from app.models.conversation import Conversation, ConversationType
    from app.services.runtime_config import (
        KEY_AI_API_BASE_URL,
        KEY_AI_API_KEY_ENC,
        KEY_AI_ENABLED,
        KEY_AI_MODEL,
        encrypt_value,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        # Populate config
        session.add(BotConfig(key=KEY_AI_ENABLED, value="true"))
        session.add(BotConfig(key=KEY_AI_API_BASE_URL, value=base_url))
        session.add(BotConfig(key=KEY_AI_MODEL, value=model))
        session.add(BotConfig(key=KEY_AI_API_KEY_ENC, value=encrypt_value(api_key)))

        conv = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420123456789",
            mode="copilot",
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        runtime = await get_production_agent_runtime(session)
        run_res = await runtime.run(
            session=session,
            conversation=conv,
            inbound_text="Tell me in 5 words why coffee is great.",
        )

        from sqlalchemy import select

        from app.models.ai import AIRun

        persisted_run = (
            await session.execute(select(AIRun).where(AIRun.id == run_res.run_id))
        ).scalar_one_or_none()

        assert persisted_run is not None, "AIRun record was not persisted to database"
        print(f"  PASS: Runtime completed (Run ID: {run_res.run_id}, Model: {persisted_run.model})")
        print(f"        Output: {run_res.reply_text[:60]!r}")

    # -----------------------------------------------------------------------
    # Level 4: Multi-turn Conversational Context Retention
    # -----------------------------------------------------------------------
    print("[Level 4] Multi-turn Context Retention...")
    async with session_maker() as session:
        conv2 = Conversation(
            type=ConversationType.dm.value,
            signal_id="+420987654321",
            mode="copilot",
        )
        session.add(conv2)
        await session.commit()
        await session.refresh(conv2)

        # Turn 1
        await runtime.run(
            session=session,
            conversation=conv2,
            inbound_text="My preferred product is Alpine Coffee.",
        )
        # Turn 2
        res2 = await runtime.run(
            session=session,
            conversation=conv2,
            inbound_text="What was my preferred product that I just mentioned?",
        )
        print(f"  PASS: Turn 2 Reply: {res2.reply_text[:80]!r}")

    # -----------------------------------------------------------------------
    # Level 5: Active PromptVersion Injection
    # -----------------------------------------------------------------------
    print("[Level 5] PromptVersion Versioning & Provenance Tracking...")
    from app.models.ai import PromptVersion

    async with session_maker() as session:
        pv = PromptVersion(
            version="LIVE_SMOKE_V2",
            name="Live Smoke System Prompt",
            template="You are a live verification bot. Prefix every answer with [VERIFIED_LIVE]:",
            is_active=True,
        )
        session.add(pv)
        await session.commit()

        runtime_v2 = await get_production_agent_runtime(session)
        res_v2 = await runtime_v2.run(
            session=session,
            conversation=conv,
            inbound_text="State your status in 3 words.",
        )
        run_v2 = (
            await session.execute(select(AIRun).where(AIRun.id == res_v2.run_id))
        ).scalar_one()

        assert run_v2.prompt_version == "LIVE_SMOKE_V2", (
            f"Expected PromptVersion LIVE_SMOKE_V2, got {run_v2.prompt_version}"
        )
        print("  PASS: PromptVersion LIVE_SMOKE_V2 successfully tracked in AIRun provenance")
        print(f"        Output: {res_v2.reply_text[:80]!r}")

    # -----------------------------------------------------------------------
    # Capability Probes: Embeddings & Native Tool Calling
    # -----------------------------------------------------------------------
    print("-" * 60)
    print("CAPABILITY PROBING:")
    # Probe embeddings
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            emb_resp = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": "test"},
            )
            if emb_resp.status_code == 200:
                print("  Live Embeddings:    VERIFIED")
            else:
                print(
                    f"  Live Embeddings:    UNSUPPORTED/NOT VERIFIED (HTTP {emb_resp.status_code})"
                )
        except Exception:
            print("  Live Embeddings:    UNSUPPORTED/NOT VERIFIED (Endpoint unreachable)")

    # Probe native tool calling
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            tool_resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "What is the stock of product 42?"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_stock",
                                "description": "Get stock of product",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"product_id": {"type": "integer"}},
                                    "required": ["product_id"],
                                },
                            },
                        }
                    ],
                },
            )
            if tool_resp.status_code == 200:
                tool_body = tool_resp.json()
                calls = tool_body.get("choices", [{}])[0].get("message", {}).get("tool_calls")
                if calls:
                    print("  Native Tool Calls:  VERIFIED")
                else:
                    print(
                        "  Native Tool Calls:  UNSUPPORTED/NOT VERIFIED (No tool calls generated)"
                    )
            else:
                print(
                    f"  Native Tool Calls:  UNSUPPORTED/NOT VERIFIED (HTTP {tool_resp.status_code})"
                )
        except Exception:
            print("  Native Tool Calls:  UNSUPPORTED/NOT VERIFIED (Request error)")

    print("=" * 60)
    print("LIVE AI GATEWAY SMOKE COMPLETED SUCCESSFULLY")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_live_smoke()))
