"""
Message Handler — processes incoming Signal messages.

Pipeline:
1. Parse raw envelope → ParsedMessage
2. Check idempotency (same Signal event already processed? skip)
3. Upsert User record (auto-create on first contact)
4. Enforce block policy (blocked users: record metadata, suppress AI/reply)
5. Upsert Group record (if group message)
6. Find or create Conversation
7. Store inbound Message in DB (idempotent)
8. Route to AI engine or manual-mode suppression
9. Write outbound Message as "pending", attempt gateway send, update status

Key fixes vs. original:
- P0-1: current user message is NOT appended to AI context again (AI builds context from DB only, excluding the just-saved message)
- P0-2: outbound message written as "pending"; status updated to "sent" or "failed" after gateway call
- P0-3: Conversation.mode is checked before AI fires — "manual" suppresses AI
- P0-4: User.is_blocked is checked; blocked users get no AI reply
- P0-5: group conversations no longer permanently attributed to first sender
- P0-6: signal_event_id dedup prevents duplicate processing on reconnect
- P1-14: group sender identity is included in AI context messages
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.conversation import Conversation, ConversationMode, Message
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
        self._ai_engine = None

    def set_ai_engine(self, engine) -> None:
        """Inject AI engine (called during startup)."""
        self._ai_engine = engine

    async def handle(self, incoming: SignalIncomingMessage) -> None:
        """
        Main entry point — called by SignalClient for each incoming message.
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

        # Build idempotency key for this inbound event
        # Format: "{sender_id}:{signal_timestamp_ms}"
        signal_event_id: str | None = None
        if parsed.sender_id and parsed.timestamp:
            signal_event_id = f"{parsed.sender_id}:{parsed.timestamp}"

        # Handle attachment-only messages (no text)
        if not parsed.text.strip() and envelope.has_attachments:
            logger.info(
                f"📎 Attachment-only message from {parsed.sender_id} — "
                f"recording metadata and sending notice"
            )
            async with async_session() as session:
                try:
                    user = await self._upsert_user(session, parsed)
                    if user.is_blocked:
                        logger.info(f"🚫 Blocked user {parsed.sender_id} sent attachment — suppressing")
                        return
                    conversation = await self._get_or_create_conversation(session, user, parsed)
                    # Record the attachment event even if we can't process the content
                    await self._store_inbound_message(
                        session, conversation, parsed,
                        content="[attachment]",
                        signal_event_id=signal_event_id,
                    )
                    await session.commit()
                except IntegrityError:
                    logger.debug(f"Duplicate attachment event suppressed: {signal_event_id}")
                    await session.rollback()
                    return
                except Exception as e:
                    logger.error(f"❌ Error recording attachment: {e}", exc_info=True)
                    await session.rollback()

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

                # Step 2: Enforce block policy
                if user.is_blocked:
                    logger.info(
                        f"🚫 Blocked user {parsed.sender_id} — "
                        f"recording message, suppressing AI and outbound reply"
                    )
                    # Still record the inbound message for audit purposes
                    conversation = await self._get_or_create_conversation(session, user, parsed)
                    await self._store_inbound_message(
                        session, conversation, parsed,
                        signal_event_id=signal_event_id,
                    )
                    await session.commit()
                    # Send read receipt for DMs (even for blocked users — we did receive it)
                    if not parsed.is_group and parsed.timestamp:
                        asyncio.create_task(
                            signal_client.send_read_receipt(
                                recipient=parsed.sender_id,
                                timestamp=parsed.timestamp,
                            )
                        )
                    return

                # Step 3: Upsert group (if applicable)
                group = None
                if parsed.is_group and parsed.group_id:
                    group = await self._upsert_group(session, parsed)

                # Step 4: Find or create conversation
                conversation = await self._get_or_create_conversation(session, user, parsed)

                # Step 5: Store the inbound message (idempotent via signal_event_id)
                try:
                    await self._store_inbound_message(
                        session, conversation, parsed,
                        signal_event_id=signal_event_id,
                    )
                    conversation.message_count += 1
                    conversation.updated_at = datetime.now()
                    if group:
                        group.total_messages += 1
                    await session.commit()
                except IntegrityError:
                    logger.debug(f"Duplicate inbound event suppressed: {signal_event_id}")
                    await session.rollback()
                    runtime_metrics.inc("message.dedup.suppressed")
                    return

                # Send read receipt for DMs (fire-and-forget)
                if not parsed.is_group and parsed.timestamp:
                    asyncio.create_task(
                        signal_client.send_read_receipt(
                            recipient=parsed.sender_id,
                            timestamp=parsed.timestamp,
                        )
                    )

                # Step 6: Check conversation mode before attempting AI reply
                if conversation.mode == ConversationMode.manual.value:
                    logger.info(
                        f"✋ Conversation #{conversation.id} in manual mode — "
                        f"AI suppressed for message from {parsed.sender_id}"
                    )
                    return

                if conversation.mode == ConversationMode.paused.value:
                    logger.info(
                        f"⏸  Conversation #{conversation.id} paused — "
                        f"no auto-reply for message from {parsed.sender_id}"
                    )
                    return

                # Step 7: Generate reply (mode == "auto")
                asyncio.create_task(
                    signal_client.show_typing(parsed.reply_recipient)
                )

                reply_text = await self._generate_reply(session, conversation, parsed)

                asyncio.create_task(
                    signal_client.hide_typing(parsed.reply_recipient)
                )

                if reply_text:
                    await self._send_outbound_reply(
                        session, conversation, reply_text, parsed.reply_recipient
                    )

            except Exception as e:
                logger.error(f"❌ Pipeline error: {e}", exc_info=True)
                await session.rollback()
            finally:
                runtime_metrics.observe_latency(
                    "message.processing",
                    time.perf_counter() - started,
                )

    async def _store_inbound_message(
        self,
        session: AsyncSession,
        conversation: Conversation,
        parsed: ParsedMessage,
        *,
        content: str | None = None,
        signal_event_id: str | None = None,
    ) -> Message:
        """Store an inbound user message. Raises IntegrityError if duplicate."""
        msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=content or parsed.text,
            sender_id=parsed.sender_id,
            sender_name=parsed.sender_name,
            signal_timestamp_ms=parsed.timestamp or None,
            signal_event_id=signal_event_id,
            delivery_status=None,  # inbound messages have no outbound status
            timestamp=datetime.fromtimestamp(parsed.timestamp / 1000)
            if parsed.timestamp
            else datetime.now(),
        )
        session.add(msg)
        await session.flush()
        return msg

    async def _send_outbound_reply(
        self,
        session: AsyncSession,
        conversation: Conversation,
        text: str,
        recipient: str,
    ) -> None:
        """
        Write outbound message as 'pending', attempt send, update status.

        This is the correct state machine:
          pending → sent  (gateway returned success)
          pending → failed (gateway returned error)

        The DB record is written first with status=pending, then updated.
        This ensures we never show a message as "sent" if the gateway failed.
        """
        # Write pending record
        bot_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=text,
            sender_id="bot",
            sender_name="Bot",
            delivery_status="pending",
            timestamp=datetime.now(),
        )
        session.add(bot_message)
        conversation.message_count += 1
        await session.commit()

        # Attempt gateway send
        try:
            ok = await signal_client.send_reply(text=text, recipient=recipient)
        except Exception as e:
            ok = False
            logger.error(f"❌ Gateway send exception: {e}")

        # Update status based on result
        if ok:
            bot_message.delivery_status = "sent"
            logger.info(f"✅ Outbound message #{bot_message.id} sent successfully")
        else:
            bot_message.delivery_status = "failed"
            bot_message.delivery_error = "gateway_send_failed"
            logger.warning(f"⚠️  Outbound message #{bot_message.id} failed to send")
            runtime_metrics.inc("message.outbound.failed")

        await session.commit()

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
            await session.flush()
            logger.info(
                f"👤 New user created: {parsed.sender_name} ({parsed.sender_id})"
            )
        else:
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
        Find an active conversation for this context, or start a new one.

        For group conversations: lookup is by group_id only.
        For DM conversations: lookup is by user_id (not signal_id, which can change).
        """
        query = select(Conversation).where(Conversation.is_active == True)  # noqa: E712

        if parsed.is_group:
            # Group conversations are identified by group_id — NOT by user
            query = query.where(Conversation.group_id == parsed.group_id)
        else:
            # DM conversations are identified by the user record
            query = (
                query
                .where(Conversation.user_id == user.id)
                .where(Conversation.group_id == None)  # noqa: E711
            )

        query = query.order_by(Conversation.updated_at.desc()).limit(1)
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                # For group conversations, user_id is NOT the definitive owner
                # It's the first sender, kept for legacy DB compat only
                user_id=user.id if not parsed.is_group else None,
                signal_id=parsed.sender_id,
                group_id=parsed.group_id,
                mode=ConversationMode.auto.value,
                is_active=True,
            )
            session.add(conversation)
            await session.flush()
            logger.debug(
                f"💬 New conversation #{conversation.id} "
                f"({'group' if parsed.is_group else 'DM'})"
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
        1. AI engine (if enabled and configured)
        2. Fallback menu/auto-reply (when AI is disabled)
        """
        if self._ai_engine is not None:
            try:
                # P0-1 FIX: pass parsed.text to AI engine.
                # The AI engine's _build_messages must NOT append user_message
                # at the end if it's already in the loaded context history.
                # See AIEngine._build_messages — history loads messages already committed,
                # then we pass user_message as the current turn. The inbound message
                # was committed BEFORE this call, so it IS in the DB history.
                # AIEngine._load_context_messages must exclude the very last message
                # (the one we just committed) to avoid duplication.
                reply = await self._ai_engine.generate_response(
                    session=session,
                    conversation=conversation,
                    user_message=parsed.text,
                    sender_name=parsed.sender_name,
                    group_id=parsed.group_id,
                    current_signal_timestamp_ms=parsed.timestamp,
                )
                if reply:
                    return reply
            except Exception as e:
                logger.error(f"❌ AI engine error: {e}", exc_info=True)

        # Fallback: basic command handling when AI is disabled
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
            select(Product).where(Product.is_active == True)  # noqa: E712
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
