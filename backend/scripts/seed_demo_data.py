"""
Safe synthetic demo data seed script for Signal Market Bot v0.4.1.
Populates clean showcase records without any private or real customer information.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models.ai import (
    AIModelCall,
    AIRun,
    AISuggestion,
    KnowledgeDocument,
    KnowledgeSource,
    MCPServerConfig,
    PromptVersion,
)
from app.models.config import BotConfig
from app.models.conversation import (
    Conversation,
    ConversationMode,
    ConversationType,
    Message,
    MessageActor,
    MessageDeliveryStatus,
    MessageDirection,
    MessageOrigin,
)
from app.models.product import Product
from app.models.user import User
from app.services.security_bootstrap import (
    KEY_ADMIN_PASSWORD_HASH,
    KEY_ADMIN_TOTP_SECRET,
    KEY_ADMIN_USERNAME,
    KEY_BOOTSTRAP_COMPLETED,
    KEY_JWT_SIGNING_SECRET,
    _hash_password,
)


async def seed():
    async with async_session() as session:
        # 1. Admin Bootstrap
        admin_pass_hash = _hash_password("AdminPass123!")
        jwt_secret = secrets.token_urlsafe(64)
        configs = {
            KEY_BOOTSTRAP_COMPLETED: "true",
            KEY_ADMIN_USERNAME: "admin",
            KEY_ADMIN_PASSWORD_HASH: admin_pass_hash,
            KEY_ADMIN_TOTP_SECRET: "",
            KEY_JWT_SIGNING_SECRET: jwt_secret,
            "ai.enabled": "true",
            "ai.provider": "openai",
            "ai.model": "gpt-4o-mini",
            "ai.base_url": "https://api.openai.com/v1",
            "ai.embedding_model": "text-embedding-3-small",
            "qdrant.enabled": "true",
            "qdrant.url": "http://localhost:6333",
            "signal.phone_number": "+420 700 000 000",
            "signal.api_url": "http://localhost:8080",
        }
        for k, v in configs.items():
            row = (
                await session.execute(select(BotConfig).where(BotConfig.key == k))
            ).scalar_one_or_none()
            if row:
                row.value = v
            else:
                session.add(
                    BotConfig(key=k, value=v, category="system", description=f"Config: {k}")
                )

        # 2. Products
        existing_products = (await session.execute(select(Product))).scalars().all()
        if not existing_products:
            p1 = Product(
                name="Alpine Coffee Beans 500g",
                description="Single-origin medium roast Arabica coffee beans",
                price=18.50,
                currency="EUR",
                stock=45,
                is_active=True,
            )
            p2 = Product(
                name="Ceramic Pour-Over Dripper",
                description="Handcrafted ceramic dripper for barista-style brew",
                price=24.00,
                currency="EUR",
                stock=20,
                is_active=True,
            )
            p3 = Product(
                name="Cold Brew Concentrate 1L",
                description="Smooth 18-hour cold brew concentrate",
                price=14.00,
                currency="EUR",
                stock=30,
                is_active=True,
            )
            session.add_all([p1, p2, p3])

        # 3. Users
        existing_users = (await session.execute(select(User))).scalars().all()
        if not existing_users:
            u1 = User(
                signal_id="+420777000123",
                phone_number="+420 777 000 123",
                display_name="Demo Customer",
                role="customer",
                language="en",
            )
            u2 = User(
                signal_id="+420777000456",
                phone_number="+420 777 000 456",
                display_name="TEST SHOWCASE USER",
                role="customer",
                language="cs",
            )
            session.add_all([u1, u2])
            await session.flush()

            # 4. Conversations
            conv1 = Conversation(
                type=ConversationType.dm.value,
                signal_id=u1.signal_id,
                dm_user_id=u1.id,
                user_id=u1.id,
                mode=ConversationMode.copilot.value,
                message_count=3,
                is_active=True,
            )
            conv2 = Conversation(
                type=ConversationType.dm.value,
                signal_id=u2.signal_id,
                dm_user_id=u2.id,
                user_id=u2.id,
                mode=ConversationMode.auto.value,
                message_count=2,
                is_active=True,
            )
            session.add_all([conv1, conv2])
            await session.flush()

            # 5. Messages
            now = datetime.now(UTC).replace(tzinfo=None)
            m1 = Message(
                conversation_id=conv1.id,
                role="user",
                sender_id=u1.signal_id,
                sender_user_id=u1.id,
                direction=MessageDirection.inbound.value,
                actor=MessageActor.customer.value,
                origin=MessageOrigin.customer.value,
                content="Hello, do you have any freshly roasted single-origin coffee beans available?",
                timestamp=now - timedelta(minutes=15),
                delivery_status=MessageDeliveryStatus.read.value,
            )
            m2 = Message(
                conversation_id=conv1.id,
                role="assistant",
                sender_id="bot",
                direction=MessageDirection.outbound.value,
                actor=MessageActor.bot.value,
                origin=MessageOrigin.human_ai_assisted.value,
                content="Yes! We just roasted a fresh batch of Alpine Coffee Beans 500g ($18.50). Would you like to place an order?",
                timestamp=now - timedelta(minutes=14),
                delivery_status=MessageDeliveryStatus.read.value,
            )
            m3 = Message(
                conversation_id=conv1.id,
                role="user",
                sender_id=u1.signal_id,
                sender_user_id=u1.id,
                direction=MessageDirection.inbound.value,
                actor=MessageActor.customer.value,
                origin=MessageOrigin.customer.value,
                content="Can I pick up an order #1042 today at the Prague store?",
                timestamp=now - timedelta(minutes=5),
                delivery_status=MessageDeliveryStatus.received.value,
            )
            session.add_all([m1, m2, m3])
            await session.flush()

            # 6. Active Prompt Version
            prompt_v1 = (
                await session.execute(
                    select(PromptVersion).where(PromptVersion.version == "v1.0.0")
                )
            ).scalar_one_or_none()
            if not prompt_v1:
                prompt_v1 = PromptVersion(
                    version="v1.0.0",
                    name="Default Customer Assistant Prompt",
                    template="You are the friendly AI assistant for Alpine Coffee & Market. Answer customer questions concisely.",
                    is_active=True,
                    created_by="admin",
                )
                session.add(prompt_v1)
                await session.flush()

            # 7. AI Runs & AIModelCalls
            run1 = AIRun(
                trace_id=f"trc_{secrets.token_hex(12)}",
                conversation_id=conv1.id,
                final_message_id=m1.id,
                traffic_source="production",
                model="gpt-4o-mini",
                provider="openai",
                prompt_version=prompt_v1.version,
                decision="reply",
                latency_ms=342,
                tokens=233,
                input_tokens=185,
                output_tokens=48,
                total_tokens=233,
                usage_source="provider",
                estimated_cost=0.000042,
                cost_currency="USD",
                llm_call_count=1,
                created_at=now - timedelta(minutes=14),
            )
            run2 = AIRun(
                trace_id=f"trc_{secrets.token_hex(12)}",
                conversation_id=conv1.id,
                final_message_id=m3.id,
                traffic_source="production",
                model="gpt-4o-mini",
                provider="openai",
                prompt_version=prompt_v1.version,
                decision="draft_for_human",
                latency_ms=286,
                tokens=275,
                input_tokens=210,
                output_tokens=65,
                total_tokens=275,
                usage_source="provider",
                estimated_cost=0.000051,
                cost_currency="USD",
                llm_call_count=1,
                created_at=now - timedelta(minutes=5),
            )
            session.add_all([run1, run2])
            await session.flush()

            # Model calls
            call1 = AIModelCall(
                ai_run_id=run1.id,
                phase="response_generation",
                provider="openai",
                model="gpt-4o-mini",
                latency_ms=335,
                input_tokens=185,
                output_tokens=48,
                total_tokens=233,
                usage_source="provider",
                success=True,
                started_at=now - timedelta(minutes=14),
            )
            call2 = AIModelCall(
                ai_run_id=run2.id,
                phase="tool_planner",
                provider="openai",
                model="gpt-4o-mini",
                latency_ms=280,
                input_tokens=210,
                output_tokens=65,
                total_tokens=275,
                usage_source="provider",
                success=True,
                started_at=now - timedelta(minutes=5),
            )
            session.add_all([call1, call2])

            # Copilot Suggestion for m3
            sug = AISuggestion(
                conversation_id=conv1.id,
                inbound_message_id=m3.id,
                ai_run_id=run2.id,
                suggested_text="Hi! Order #1042 is packaged and ready for pickup at our Prague store counter until 6:00 PM today.",
                status="pending",
                generated_at=now - timedelta(minutes=5),
            )
            session.add(sug)

        # 8. Knowledge Source
        existing_ks = (await session.execute(select(KnowledgeSource))).scalars().all()
        if not existing_ks:
            ks = KnowledgeSource(
                title="Store Operations & Return Policy",
                source_type="faq",
                language="en",
                status="active",
            )
            session.add(ks)
            await session.flush()

            kd1 = KnowledgeDocument(
                source_id=ks.id,
                title="Return & Refund Window FAQ",
                scope_type="global",
                chunk_count=2,
                content="Unopened coffee beans and equipment in original packaging may be returned within 14 days of purchase with receipt.",
            )
            kd2 = KnowledgeDocument(
                source_id=ks.id,
                title="Store Locations & Working Hours",
                scope_type="global",
                chunk_count=2,
                content="Prague Central Store: Monday to Saturday, 8:00 AM - 6:00 PM. Order pickups ready within 2 hours.",
            )
            session.add_all([kd1, kd2])

        # 9. MCP Server
        existing_mcp = (await session.execute(select(MCPServerConfig))).scalars().all()
        if not existing_mcp:
            mcp = MCPServerConfig(
                name="Store Inventory Service",
                transport="stdio",
                command_or_url="python3",
                args_json='["-m", "app.tools.inventory"]',
                is_enabled=True,
                status="connected",
                last_connected_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(mcp)

        await session.commit()
        print("Seed data completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
