#!/usr/bin/env python3
"""
Live external AI gateway smoke test runner.

Validates end-to-end compatibility against a real OpenAI-compatible endpoint.
Reads configuration from environment variables or local DB runtime configuration:
  LIVE_AI_BASE_URL (required or via --use-db-config)
  LIVE_AI_MODEL    (required or via --use-db-config)
  LIVE_AI_API_KEY  (required or via --use-db-config; never logged, never leaked)

Exit codes:
  0: PASS or SKIPPED_NO_CREDENTIALS (when --require-live is not set)
  1: FAIL (test failed during execution)
  2: MISSING_CREDENTIALS (when --require-live is set and credentials are absent)

Levels verified:
  Level 1: Raw gateway HTTP chat completion + token telemetry parsing
  Level 2: OpenAICompatibleProvider adapter returning structured LLMResult
  Level 3: Production AgentRuntime factory + AgentContext + AIRun persistence
  Level 4: Multi-turn conversational context retention
  Level 5: Active PromptVersion injection & provenance tracking
  Capability Probe: Embeddings and native tool calling support
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx


async def load_credentials_from_db() -> tuple[str, str, str]:
    """Attempt to load AI credentials from bot_config table."""
    # Ensure master key can be found even if executed from backend/
    import app.services.runtime_config as rc

    if not rc._MASTER_KEY_CACHE:
        for candidate_key in ["../data/.master_key", "data/.master_key"]:
            if os.path.exists(candidate_key):
                try:
                    with open(candidate_key, encoding="utf-8") as f:
                        k = f.read().strip()
                        if k:
                            rc._MASTER_KEY_CACHE = k
                            break
                except Exception:
                    pass

    try:
        from sqlalchemy import select

        from app.database import async_session
        from app.models.config import BotConfig
        from app.services.runtime_config import (
            KEY_AI_API_BASE_URL,
            KEY_AI_API_KEY_ENC,
            KEY_AI_MODEL,
            decrypt_value,
        )

        async with async_session() as session:
            rows = (await session.execute(select(BotConfig))).scalars().all()
            cfg = {r.key: r.value for r in rows}
            base_url = cfg.get(KEY_AI_API_BASE_URL, "").strip()
            model = cfg.get(KEY_AI_MODEL, "").strip()
            enc_key = cfg.get(KEY_AI_API_KEY_ENC, "").strip()
            api_key = decrypt_value(enc_key) if enc_key else ""
            if base_url and model and api_key:
                return base_url, model, api_key
    except Exception:
        pass

    # Check fallback path ../data/bot.db if run from backend/
    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.config import BotConfig
        from app.services.runtime_config import (
            KEY_AI_API_BASE_URL,
            KEY_AI_API_KEY_ENC,
            KEY_AI_MODEL,
            decrypt_value,
        )

        for candidate in ["../data/bot.db", "data/bot.db"]:
            if os.path.exists(candidate):
                engine = create_async_engine(f"sqlite+aiosqlite:///{os.path.abspath(candidate)}")
                session_maker = async_sessionmaker(engine, expire_on_commit=False)
                async with session_maker() as session:
                    rows = (await session.execute(select(BotConfig))).scalars().all()
                    cfg = {r.key: r.value for r in rows}
                    base_url = cfg.get(KEY_AI_API_BASE_URL, "").strip()
                    model = cfg.get(KEY_AI_MODEL, "").strip()
                    enc_key = cfg.get(KEY_AI_API_KEY_ENC, "").strip()
                    api_key = decrypt_value(enc_key) if enc_key else ""
                    if base_url and model and api_key:
                        return base_url, model, api_key
    except Exception:
        pass

    return "", "", ""


async def run_live_smoke(
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    require_live: bool = False,
    use_db_config: bool = False,
) -> int:
    env_base_url = os.environ.get("LIVE_AI_BASE_URL", "").strip().rstrip("/")
    env_model = os.environ.get("LIVE_AI_MODEL", "").strip()
    env_api_key = os.environ.get("LIVE_AI_API_KEY", "").strip()

    base_url = (base_url or env_base_url).strip().rstrip("/")
    model = (model or env_model).strip()
    api_key = (api_key or env_api_key).strip()

    if (not api_key or not base_url or not model) and use_db_config:
        db_url, db_model, db_key = await load_credentials_from_db()
        base_url = base_url or db_url
        model = model or db_model
        api_key = api_key or db_key

    if not api_key or not base_url or not model:
        print("=" * 65)
        print("LIVE AI SMOKE: SKIPPED (NO CREDENTIALS SUPPLIED)")
        print("=" * 65)
        print(f"Target Gateway: {base_url or '(Not configured)'}")
        print(f"Target Model:   {model or '(Not configured)'}")
        print("Status:         SKIPPED_NO_CREDENTIALS")
        print("Notice:         Required credentials were not provided.")
        print("                Set LIVE_AI_BASE_URL, LIVE_AI_MODEL, LIVE_AI_API_KEY")
        print("                or pass --use-db-config to load saved encrypted DB settings.")
        print("=" * 65)
        if require_live:
            print("ERROR: --require-live specified but credentials are missing.")
            return 2
        return 0

    # Normalize OpenAI-compatible endpoint url if it doesn't end with /v1
    effective_base_url = base_url
    if not effective_base_url.endswith("/v1"):
        effective_base_url = f"{effective_base_url}/v1"

    masked_key = f"{api_key[:3]}...{api_key[-3:]}" if len(api_key) > 6 else "***"
    print("=" * 65)
    print("STARTING LIVE AI GATEWAY SMOKE")
    print("=" * 65)
    print(f"Base URL: {effective_base_url}")
    print(f"Model:    {model}")
    print(f"Key:      {masked_key} (masked)")
    print("-" * 65)

    # -----------------------------------------------------------------------
    # Level 1: Raw Gateway HTTP Chat Completion + Token Telemetry
    # -----------------------------------------------------------------------
    print("[Level 1] Raw Gateway HTTP Chat Completion & Token Telemetry...")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            resp = await client.post(
                f"{effective_base_url}/chat/completions",
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
            choice = body.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "").strip()
            finish_reason = choice.get("finish_reason")
            usage_data = body.get("usage", {})
            in_tok = usage_data.get("prompt_tokens")
            out_tok = usage_data.get("completion_tokens")
            tot_tok = usage_data.get("total_tokens")
            cached_tok = (usage_data.get("prompt_tokens_details") or {}).get("cached_tokens")
            reasoning_tok = (usage_data.get("completion_tokens_details") or {}).get(
                "reasoning_tokens"
            )

            print(f"  PASS: HTTP 200 ({lat1}ms) - Preview: {content!r}")
            print(f"        Finish Reason: {finish_reason}")
            if in_tok is not None or out_tok is not None or tot_tok is not None:
                print(
                    f"        Tokens: in={in_tok}, out={out_tok}, total={tot_tok} (cached={cached_tok}, reasoning={reasoning_tok})"
                )
            else:
                print("        Tokens: unavailable from provider")
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            return 1

    # -----------------------------------------------------------------------
    # Level 2: OpenAICompatibleProvider Adapter
    # -----------------------------------------------------------------------
    print("[Level 2] OpenAICompatibleProvider Adapter...")
    from app.ai.providers.llm import OpenAICompatibleProvider
    from app.ai.types.usage import LLMResult

    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=effective_base_url,
        default_model=model,
    )
    t0 = time.perf_counter()
    try:
        gen_result = await provider.generate(
            messages=[{"role": "user", "content": "Say hello in one word."}],
            temperature=0.2,
            max_tokens=20,
        )
        lat2 = int((time.perf_counter() - t0) * 1000)
        if not isinstance(gen_result, LLMResult):
            print(f"  FAILED: Expected LLMResult, got {type(gen_result)}")
            return 1
        print(f"  PASS: Provider generated ({lat2}ms) - Result: {gen_result.content.strip()!r}")
        print(
            f"        Usage Source: {gen_result.usage.usage_source}, Total: {gen_result.usage.total_tokens}"
        )
    except Exception as e:
        print(f"  FAILED with exception: {e}")
        return 1

    # -----------------------------------------------------------------------
    # Level 3: Real Production AgentRuntime Factory + Persistence
    # -----------------------------------------------------------------------
    print("[Level 3] Production Factory + Encrypted BotConfig + AIRun persistence...")
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.ai.runtime.context import AgentContext
    from app.ai.runtime.decisions import AgentResponse
    from app.ai.runtime.factory import get_production_agent_runtime
    from app.database import Base
    from app.models.ai import AIRun
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
        session.add(BotConfig(key=KEY_AI_ENABLED, value="true"))
        session.add(BotConfig(key=KEY_AI_API_BASE_URL, value=effective_base_url))
        session.add(BotConfig(key=KEY_AI_MODEL, value=model))
        session.add(BotConfig(key=KEY_AI_API_KEY_ENC, value=encrypt_value(api_key)))

        conv = Conversation(
            id=1,
            type=ConversationType.dm.value,
            signal_id="+420123456789",
            mode="copilot",
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        runtime = await get_production_agent_runtime(session)
        context = AgentContext(
            conversation_id=conv.id,
            sender_id=conv.signal_id,
            text="Tell me in 5 words why coffee is great.",
            mode="copilot",
            traffic_source="provider_test",
        )
        run_res: AgentResponse = await runtime.run(
            session=session,
            context=context,
        )

        persisted_run = (
            await session.execute(select(AIRun).where(AIRun.id == run_res.ai_run_id))
        ).scalar_one_or_none()

        if persisted_run is None:
            print("  FAILED: AIRun record was not persisted to database")
            return 1
        if persisted_run.traffic_source != "provider_test":
            print(f"  FAILED: Unexpected traffic source: {persisted_run.traffic_source}")
            return 1
        print(
            f"  PASS: Runtime completed (Run ID: {run_res.ai_run_id}, Model: {persisted_run.model})"
        )
        print(f"        Output: {run_res.answer[:60]!r}")
        print(
            f"        Persisted Usage: in={persisted_run.input_tokens}, out={persisted_run.output_tokens}, total={persisted_run.total_tokens}, source={persisted_run.usage_source}"
        )

    # -----------------------------------------------------------------------
    # Level 4: Multi-turn Context Retention
    # -----------------------------------------------------------------------
    print("[Level 4] Multi-turn Context Retention...")
    async with session_maker() as session:
        conv2 = Conversation(
            id=2,
            type=ConversationType.dm.value,
            signal_id="+420987654321",
            mode="copilot",
        )
        session.add(conv2)
        await session.commit()
        await session.refresh(conv2)

        # Turn 1
        ctx1 = AgentContext(
            conversation_id=conv2.id,
            sender_id=conv2.signal_id,
            text="My preferred product is Alpine Coffee.",
            mode="copilot",
            traffic_source="provider_test",
        )
        res1 = await runtime.run(session=session, context=ctx1)

        # Turn 2 with history
        ctx2 = AgentContext(
            conversation_id=conv2.id,
            sender_id=conv2.signal_id,
            text="What was my preferred product that I just mentioned?",
            mode="copilot",
            traffic_source="provider_test",
            recent_messages=[
                {"direction": "incoming", "body": "My preferred product is Alpine Coffee."},
                {"direction": "outgoing", "body": res1.answer},
            ],
        )
        res2 = await runtime.run(session=session, context=ctx2)
        ans_lower = res2.answer.lower()
        has_alpine_coffee = "alpine coffee" in ans_lower or (
            "alpine" in ans_lower and "coffee" in ans_lower
        )
        if not has_alpine_coffee:
            print(f"  FAILED: Turn 2 reply did not identify 'Alpine Coffee': {res2.answer[:80]!r}")
            return 1
        print(f"  PASS: Turn 2 context retained (Alpine Coffee): {res2.answer[:80]!r}")

    # -----------------------------------------------------------------------
    # Level 5: Active PromptVersion Injection & Provenance Tracking
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
        ctx_v2 = AgentContext(
            conversation_id=conv.id,
            sender_id=conv.signal_id,
            text="State your status in 3 words.",
            mode="copilot",
            traffic_source="provider_test",
        )
        res_v2 = await runtime_v2.run(session=session, context=ctx_v2)
        run_v2 = (
            await session.execute(select(AIRun).where(AIRun.id == res_v2.ai_run_id))
        ).scalar_one()

        if run_v2.prompt_version != "LIVE_SMOKE_V2":
            print(f"  FAILED: Expected PromptVersion LIVE_SMOKE_V2, got {run_v2.prompt_version}")
            return 1
        print("  PASS: PromptVersion LIVE_SMOKE_V2 successfully tracked in AIRun provenance")
        print(f"        Output: {res_v2.answer[:80]!r}")

    # -----------------------------------------------------------------------
    # Capability Probes: Embeddings & Native Tool Calling
    # -----------------------------------------------------------------------
    print("-" * 65)
    print("CAPABILITY PROBING:")
    # Probe embeddings
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        try:
            emb_resp = await client.post(
                f"{effective_base_url}/embeddings",
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
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        try:
            tool_resp = await client.post(
                f"{effective_base_url}/chat/completions",
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

    print("=" * 65)
    print("LIVE AI GATEWAY SMOKE COMPLETED SUCCESSFULLY")
    print("=" * 65)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live AI Gateway Smoke Test Runner")
    parser.add_argument("--base-url", help="Target API Base URL (defaults to LIVE_AI_BASE_URL)")
    parser.add_argument("--model", help="Target Model Name (defaults to LIVE_AI_MODEL)")
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Exit with code 2 if credentials are not provided",
    )
    parser.add_argument(
        "--use-db-config",
        action="store_true",
        help="Attempt to load saved encrypted DB configuration if env is empty",
    )
    args = parser.parse_args()

    return asyncio.run(
        run_live_smoke(
            base_url=args.base_url,
            model=args.model,
            api_key=None,
            require_live=args.require_live,
            use_db_config=args.use_db_config,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
