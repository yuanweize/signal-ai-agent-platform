"""
Message Handler — processes incoming Signal messages.

Pipeline:
1. Parse raw envelope → ParsedMessage
2. Upsert User record (auto-create on first contact)
3. Upsert Group record (if group message)
4. Find or create Conversation
5. Store Message in DB
6. Route to AI engine (Phase 3) or echo for now
7. Send reply via SignalClient
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.conversation import Conversation, Message
from app.models.group import Group
from app.models.user import User
from app.models.product import Product
from app.schemas.signal import ParsedMessage, SignalIncomingMessage
from app.services.signal_client import signal_client
from app.services.metrics import runtime_metrics

logger = logging.getLogger("signal.handler")


class MessageHandler:
    """
    Processes incoming Signal messages through the full pipeline.

    Registered as the callback on SignalClient.on_message.
    """

    def __init__(self) -> None:
        # Phase 3 will inject the AI engine here
        self._ai_engine = None

    def set_ai_engine(self, engine) -> None:
        """Inject AI engine (called during Phase 3 setup)."""
        self._ai_engine = engine

    async def handle(self, incoming: SignalIncomingMessage) -> None:
        """
        Main entry point — called by SignalClient for each incoming message.

        Args:
            incoming: Raw parsed message from the Signal API
        """
        started = time.perf_counter()
        envelope = incoming.envelope

        # Build normalized internal message
        parsed = ParsedMessage(
            sender_id=envelope.sender_id,
            sender_name=envelope.sender_name,
            text=envelope.text or "",
            group_id=envelope.group_id,
            timestamp=envelope.timestamp,
            is_group=envelope.is_group_message,
        )

        # Send read receipt for DMs (fire-and-forget, non-blocking)
        if not parsed.is_group and parsed.timestamp:
            asyncio.create_task(
                signal_client.send_read_receipt(
                    recipient=parsed.sender_id,
                    timestamp=parsed.timestamp,
                )
            )

        # Handle attachment-only messages (no text)
        if not parsed.text.strip() and envelope.has_attachments:
            logger.info(
                f"📎 Attachment-only message from {parsed.sender_id} — replying with notice"
            )
            await signal_client.send_reply(
                text="📎 Děkujeme za soubor. Přílohy zatím nepodporujeme. "
                     "Napište prosím textovou zprávu.\n"
                     "(Thank you for the file. Attachments are not yet supported. "
                     "Please send a text message.)",
                recipient=parsed.reply_recipient,
            )
            return

        if not parsed.text.strip():
            logger.debug(f"Skipping empty message from {parsed.sender_id}")
            return

        # Process through the pipeline
        async with async_session() as session:
            try:
                # Step 1: Upsert user
                user = await self._upsert_user(session, parsed)

                # Step 2: Upsert group (if applicable)
                group = None
                if parsed.is_group and parsed.group_id:
                    group = await self._upsert_group(session, parsed)

                # Step 3: Find or create conversation
                conversation = await self._get_or_create_conversation(
                    session, user, parsed
                )

                # Step 4: Store the incoming message
                user_message = Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=parsed.text,
                    sender_id=parsed.sender_id,
                    timestamp=datetime.fromtimestamp(parsed.timestamp / 1000)
                    if parsed.timestamp
                    else datetime.now(),
                )
                session.add(user_message)

                # Update conversation stats
                conversation.message_count += 1
                conversation.updated_at = datetime.now()

                # Update group stats if applicable
                if group:
                    group.total_messages += 1

                await session.commit()

                # Step 5: Generate reply (with typing indicator)
                # Show typing indicator while AI processes
                asyncio.create_task(
                    signal_client.show_typing(parsed.reply_recipient)
                )

                reply_text = await self._generate_reply(session, conversation, parsed)

                # Hide typing indicator after response
                asyncio.create_task(
                    signal_client.hide_typing(parsed.reply_recipient)
                )

                if reply_text:
                    # Step 6: Store bot's reply in DB
                    bot_message = Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=reply_text,
                        sender_id="bot",
                    )
                    session.add(bot_message)
                    conversation.message_count += 1
                    await session.commit()

                    # Step 7: Send reply via Signal
                    await signal_client.send_reply(
                        text=reply_text,
                        recipient=parsed.reply_recipient,
                    )

            except Exception as e:
                logger.error(f"❌ Pipeline error: {e}", exc_info=True)
                await session.rollback()
            finally:
                runtime_metrics.observe_latency(
                    "message.processing",
                    time.perf_counter() - started,
                )

    async def _upsert_user(
        self, session: AsyncSession, parsed: ParsedMessage
    ) -> User:
        """Find existing user or create new one on first contact."""
        result = await session.execute(
            select(User).where(User.signal_id == parsed.sender_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                signal_id=parsed.sender_id,
                display_name=parsed.sender_name,
                language=settings.bot_default_language,
            )
            session.add(user)
            await session.flush()  # Get the ID
            logger.info(
                f"👤 New user created: {parsed.sender_name} ({parsed.sender_id})"
            )
        else:
            # Update last seen and name if changed
            user.last_seen = datetime.now()
            if parsed.sender_name and parsed.sender_name != user.display_name:
                user.display_name = parsed.sender_name

        return user

    async def _upsert_group(
        self, session: AsyncSession, parsed: ParsedMessage
    ) -> Group:
        """Find existing group or register it on first encounter."""
        result = await session.execute(
            select(Group).where(Group.group_id == parsed.group_id)
        )
        group = result.scalar_one_or_none()

        if group is None:
            group = Group(
                group_id=parsed.group_id,
                name=f"Group {parsed.group_id[:8]}...",
                is_active=True,
            )
            session.add(group)
            await session.flush()
            logger.info(f"👥 New group registered: {group.group_id}")
        else:
            group.last_activity = datetime.now()

        return group

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        user: User,
        parsed: ParsedMessage,
    ) -> Conversation:
        """
        Find an active conversation for this user (+group), or start a new one.

        Conversations are grouped by user + group_id.
        A new conversation starts if none exists or if the last one
        has been inactive for a long time (configurable).
        """
        query = select(Conversation).where(Conversation.is_active == True)  # noqa: E712

        if parsed.is_group:
            query = query.where(Conversation.group_id == parsed.group_id)
        else:
            query = query.where(Conversation.user_id == user.id).where(Conversation.group_id == None)  # noqa: E711

        query = query.order_by(Conversation.updated_at.desc()).limit(1)
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                user_id=user.id,
                signal_id=parsed.sender_id,
                group_id=parsed.group_id,
                is_active=True,
            )
            session.add(conversation)
            await session.flush()
            logger.debug(
                f"💬 New conversation #{conversation.id} for {parsed.sender_id}"
            )

        return conversation

    async def _generate_reply(
        self,
        session: AsyncSession,
        conversation: Conversation,
        parsed: ParsedMessage,
    ) -> str | None:
        """
        Generate a reply based on available modules.

        Priority:
        1. AI engine (if FEATURE_AI_ENABLED and key configured)
        2. No reply (log-only mode when AI is disabled)

        Each module is independent — disabling AI doesn't affect
        message logging, user tracking, or other features.
        """
        # AI module: only if enabled and injected
        if self._ai_engine is not None:
            try:
                reply = await self._ai_engine.generate_response(
                    session=session,
                    conversation=conversation,
                    user_message=parsed.text,
                    group_id=parsed.group_id,
                )
                # Track token usage on the stored message
                if reply and hasattr(self._ai_engine, "last_tokens_used"):
                    tokens = self._ai_engine.last_tokens_used
                    if tokens:
                        # Token count will be stored by the caller
                        pass
                if reply:
                    return reply
            except Exception as e:
                logger.error(f"❌ AI engine error: {e}", exc_info=True)
                # Continue to fallback response instead of silent drop

        # No AI available — fallback to basic auto-reply commands
        text_lower = parsed.text.lower().strip()
        keywords = ["menu", "produkty", "ceník", "nabídka", "products", "help", "pomoc", "/menu", "/start"]
        
        if any(text_lower == k for k in keywords) or any(k in text_lower.split() for k in keywords):
            return await self._generate_fallback_menu(session)

        logger.info(
            f"📝 [Fallback] Message from {parsed.sender_name} stored "
            f"(AI module disabled). Sending availability notice."
        )
        return (
            "✅ Zpráva dorazila. AI asistent je momentálně vypnutý.\n"
            "Napište prosím *menu* pro zobrazení nabídky, nebo vyčkejte na manuální odpověď."
        )

    async def _generate_fallback_menu(self, session: AsyncSession) -> str:
        """Generate a simple text menu of active products when AI is disabled."""
        result = await session.execute(
            select(Product).where(Product.is_active == True)
        )
        products = result.scalars().all()
        
        if not products:
            return "📦 Náš katalog je momentálně prázdný. (Our catalog is currently empty.)"
            
        lines = ["📦 *Naše Nabídka* (Our Menu):\n"]
        for p in products:
            lines.append(f"• {p.name}")
            if p.description:
                lines.append(f"  {p.description}")
            lines.append(f"  Cena: {p.price} {p.currency}\n")
            
        lines.append("🤖 AI asistent je momentálně vypnutý. Majitel vám brzy odpoví osobně.")
        return "\n".join(lines)


# ---- Singleton instance ----
message_handler = MessageHandler()

