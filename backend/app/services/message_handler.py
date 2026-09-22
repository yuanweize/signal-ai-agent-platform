"""
Message Handler — processes incoming Signal messages.

Pipeline:
1. Parse raw envelope -> ParsedMessage
2. Check idempotency (same Signal event already processed? skip)
3. Upsert User record and UserIdentity
4. Handle reaction-only events (persist MessageReaction, skip AI)
5. Handle attachment events (persist Message and MessageAttachment rows)
6. Enforce block policy (blocked users: record metadata, suppress AI/reply)
7. Upsert Group record & GroupMember roster (if group message)
8. Find or create Conversation (type="dm" | "group", no single user owner for group)
9. Store inbound Message in DB (idempotent, sender_user_id mapped)
10. Check conversation mode (auto | manual | paused)
11. Generate AI reply (or fallback)
12. Race check: re-verify conversation mode before sending reply; if admin took over, discard AI reply!
13. Deliver outbound reply via OutboundMessageService (state machine: pending -> sent | failed)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.conversation import (
    Conversation,
    ConversationMode,
    ConversationType,
    Message,
    MessageActor,
    MessageAttachment,
    MessageDeliveryStatus,
    MessageDirection,
    MessageOrigin,
    MessageReaction,
)
from app.models.group import Group, GroupMember
from app.models.product import Product
from app.models.user import User, UserIdentity
from app.schemas.signal import ParsedMessage, SignalIncomingMessage
from app.services.metrics import runtime_metrics
from app.services.outbound_service import outbound_service
from app.services.signal_client import signal_client

logger = logging.getLogger("services.message_handler")


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class MessageHandler:
    """Processes incoming Signal messages through the full pipeline."""

    def __init__(self) -> None:
        self._agent_runtime = None

    def set_agent_runtime(self, runtime) -> None:
        """Inject AgentRuntime (for testing or runtime override)."""
        self._agent_runtime = runtime

    async def handle_message(self, incoming: SignalIncomingMessage) -> None:
        """Alias for handle."""
        await self.handle(incoming)

    handle_envelope = handle_message

    async def handle(self, incoming: SignalIncomingMessage) -> None:
        """Main entry point — called for each incoming message."""
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

        signal_event_id: str | None = None
        if parsed.sender_id and parsed.timestamp:
            signal_event_id = f"{parsed.sender_id}:{parsed.timestamp}"

        # -------------------------------------------------------------
        # Handle Reaction-only events (Section 17)
        # -------------------------------------------------------------
        if envelope.has_reaction and not parsed.text.strip():
            reaction = envelope.data_message.reaction  # type: ignore
            logger.info(f"👍 Reaction received: {reaction.emoji} from {parsed.sender_id}")
            async with async_session() as session:
                try:
                    user = await self._upsert_user(session, parsed)
                    if parsed.is_group and parsed.group_id:
                        await self._upsert_group_and_member(session, parsed, user)
                    conversation = await self._get_or_create_conversation(session, user, parsed)

                    # Resolve target message by target timestamp
                    target_q = select(Message).where(Message.conversation_id == conversation.id)
                    if reaction.target_timestamp:
                        target_q = target_q.where(
                            Message.signal_timestamp_ms == reaction.target_timestamp
                        )
                    target_res = await session.execute(
                        target_q.order_by(Message.timestamp.desc()).limit(1)
                    )
                    target_msg = target_res.scalar_one_or_none()

                    if target_msg:
                        rx = MessageReaction(
                            message_id=target_msg.id,
                            emoji=reaction.emoji,
                            reactor_identity=parsed.sender_id,
                            reactor_user_id=user.id,
                            target_author=reaction.target_author,
                            target_timestamp=reaction.target_timestamp,
                            is_removed=reaction.is_remove,
                            occurred_at=datetime.fromtimestamp(parsed.timestamp / 1000)
                            if parsed.timestamp
                            else utc_now(),
                        )
                        session.add(rx)
                        await session.commit()
                        logger.info(
                            f"✅ Reaction {reaction.emoji} saved for message #{target_msg.id}"
                        )
                except Exception as e:
                    logger.error(f"❌ Error recording reaction: {e}", exc_info=True)
                    await session.rollback()
            return

        # -------------------------------------------------------------
        # Handle Attachment-only messages (Section 18)
        # -------------------------------------------------------------
        if not parsed.text.strip() and envelope.has_attachments:
            logger.info(f"📎 Attachment-only message from {parsed.sender_id}")
            async with async_session() as session:
                try:
                    user = await self._upsert_user(session, parsed)
                    if parsed.is_group and parsed.group_id:
                        await self._upsert_group_and_member(session, parsed, user)
                    conversation = await self._get_or_create_conversation(session, user, parsed)

                    if user.is_blocked:
                        logger.info(
                            f"🚫 Blocked user {parsed.sender_id} sent attachment — recording only"
                        )
                        msg = await self._store_inbound_message(
                            session,
                            conversation,
                            parsed,
                            user=user,
                            content="[attachment]",
                            signal_event_id=signal_event_id,
                        )
                        self._store_attachments(session, msg, envelope)
                        await session.commit()
                        return

                    msg = await self._store_inbound_message(
                        session,
                        conversation,
                        parsed,
                        user=user,
                        content="[attachment]",
                        signal_event_id=signal_event_id,
                    )
                    self._store_attachments(session, msg, envelope)
                    conversation.message_count += 1
                    conversation.last_message_at = utc_now()
                    await session.commit()
                except IntegrityError:
                    logger.debug(f"Duplicate attachment event suppressed: {signal_event_id}")
                    await session.rollback()
                    return
                except Exception as e:
                    logger.error(f"❌ Error recording attachment: {e}", exc_info=True)
                    await session.rollback()
                    return

                # Send helpful notice if in auto mode
                if conversation.mode == ConversationMode.auto.value:
                    await outbound_service.send_message(
                        session=session,
                        conversation_id=conversation.id,
                        content="📎 Děkujeme za soubor. Přílohy zatím nepodporujeme. Napište prosím textovou zprávu.\n(Thank you for the file. Attachments are not yet supported. Please send a text message.)",
                        recipient=parsed.reply_recipient,
                        actor=MessageActor.bot.value,
                    )
            return

        if not parsed.text.strip():
            logger.debug(f"Skipping empty message from {parsed.sender_id}")
            return

        # -------------------------------------------------------------
        # Full Text / Inbound Pipeline
        # -------------------------------------------------------------
        async with async_session() as session:
            try:
                # 1. Upsert User and Identity
                user = await self._upsert_user(session, parsed)

                # 2. Upsert Group & Membership
                group = None
                if parsed.is_group and parsed.group_id:
                    group, _ = await self._upsert_group_and_member(session, parsed, user)

                # 3. Find or create Conversation
                conversation = await self._get_or_create_conversation(session, user, parsed)

                # 4. Check Block Policy
                if user.is_blocked:
                    logger.info(
                        f"🚫 Blocked user {parsed.sender_id} — recording message, suppressing AI"
                    )
                    await self._store_inbound_message(
                        session, conversation, parsed, user=user, signal_event_id=signal_event_id
                    )
                    await session.commit()
                    return

                # 5. Store inbound message
                try:
                    inbound_msg = await self._store_inbound_message(
                        session, conversation, parsed, user=user, signal_event_id=signal_event_id
                    )
                    if envelope.has_attachments:
                        self._store_attachments(session, inbound_msg, envelope)

                    conversation.message_count += 1
                    conversation.last_message_at = utc_now()
                    conversation.updated_at = utc_now()
                    if group:
                        group.total_messages += 1
                        group.last_activity = utc_now()
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

                # 6. Check conversation mode
                if conversation.mode == ConversationMode.manual.value:
                    logger.info(
                        f"✋ Conversation #{conversation.id} in manual mode — AI suppressed"
                    )
                    return

                if conversation.mode == ConversationMode.paused.value:
                    logger.info(f"⏸ Conversation #{conversation.id} paused — auto-reply suppressed")
                    return

                # 7. Unified AI Agent Execution (Auto & Copilot share AgentRuntime)
                from app.ai.runtime.context import AgentContext
                from app.ai.runtime.decisions import AgentDecision
                from app.ai.runtime.factory import get_production_agent_runtime
                from app.services.runtime_config import get_runtime_settings

                runtime_settings = await get_runtime_settings(session)
                is_ai_enabled = bool(runtime_settings.get("is_ai_enabled"))

                # In non-injected runtime, respect explicit AI-disabled toggle
                if not is_ai_enabled and not self._agent_runtime:
                    if conversation.mode == ConversationMode.auto.value:
                        text_lower = (parsed.text or "").lower().strip()
                        keywords = [
                            "menu",
                            "produkty",
                            "ceník",
                            "nabídka",
                            "products",
                            "help",
                            "pomoc",
                            "/menu",
                            "/start",
                        ]
                        if any(text_lower == k for k in keywords) or any(
                            k in text_lower.split() for k in keywords
                        ):
                            menu_reply = await self._generate_fallback_menu(session)
                            await outbound_service.send_message(
                                session=session,
                                conversation_id=conversation.id,
                                content=menu_reply,
                                recipient=parsed.reply_recipient,
                                actor=MessageActor.bot.value,
                                origin=MessageOrigin.rule_keyword.value,
                            )
                        else:
                            logger.info(
                                f"AI disabled in Settings — auto reply suppressed for conv #{conversation.id}"
                            )
                    return

                runtime = self._agent_runtime or await get_production_agent_runtime(session)

                context = AgentContext(
                    conversation_id=conversation.id,
                    message_id=inbound_msg.id,
                    sender_id=parsed.sender_id,
                    user_id=user.id if user else None,
                    text=parsed.text,
                    is_group=parsed.is_group,
                    group_id=parsed.group_id,
                    mode=conversation.mode,
                )

                async def _safe_typing(coro):
                    try:
                        await coro
                    except Exception:
                        pass

                asyncio.create_task(_safe_typing(signal_client.show_typing(parsed.reply_recipient)))
                try:
                    agent_response = await runtime.run(session, context)
                finally:
                    asyncio.create_task(
                        _safe_typing(signal_client.hide_typing(parsed.reply_recipient))
                    )

                if conversation.mode == ConversationMode.copilot.value:
                    logger.info(
                        f"🤖 Conversation #{conversation.id} in copilot mode — "
                        f"drafted suggestion #{agent_response.ai_suggestion_id}"
                    )
                    return

                # In Auto mode: check decision
                if agent_response.decision == AgentDecision.reply.value and agent_response.answer:
                    # 8. RACE CONDITION CHECK (Section 25)
                    # Re-query authoritative conversation mode before sending in case admin switched to manual mid-generation!
                    await session.refresh(conversation)
                    if conversation.mode != ConversationMode.auto.value:
                        logger.info(
                            f"✋ Admin switched conversation #{conversation.id} to mode '{conversation.mode}' "
                            f"during AI generation — discarding outbound reply!"
                        )
                        if agent_response.ai_suggestion_id:
                            from app.models.ai import AISuggestion, AISuggestionStatus

                            sug_to_expire = await session.get(
                                AISuggestion, agent_response.ai_suggestion_id
                            )
                            if sug_to_expire:
                                sug_to_expire.status = AISuggestionStatus.expired.value
                                await session.commit()
                        return

                    # 9. Deliver Outbound Reply via OutboundMessageService with Provenance
                    from app.models.ai import AIRun, AISuggestion, AISuggestionStatus

                    outbound_msg = await outbound_service.send_message(
                        session=session,
                        conversation_id=conversation.id,
                        content=agent_response.answer,
                        recipient=parsed.reply_recipient,
                        actor=MessageActor.bot.value,
                        origin=MessageOrigin.ai_auto.value,
                        ai_run_id=agent_response.ai_run_id,
                        ai_suggestion_id=agent_response.ai_suggestion_id,
                        tokens_used=agent_response.tokens,
                        model=agent_response.model,
                        prompt_version=agent_response.prompt_version,
                    )

                    # Update suggestion & run finalization based on real network send outcome
                    if outbound_msg.delivery_status == MessageDeliveryStatus.sent.value:
                        if agent_response.ai_suggestion_id:
                            sug_to_update = await session.get(
                                AISuggestion, agent_response.ai_suggestion_id
                            )
                            if sug_to_update:
                                sug_to_update.status = AISuggestionStatus.auto_sent.value
                                sug_to_update.final_message_id = outbound_msg.id
                        if agent_response.ai_run_id:
                            run_to_update = await session.get(AIRun, agent_response.ai_run_id)
                            if run_to_update:
                                run_to_update.final_message_id = outbound_msg.id
                        await session.commit()
                    else:
                        if agent_response.ai_suggestion_id:
                            sug_to_update = await session.get(
                                AISuggestion, agent_response.ai_suggestion_id
                            )
                            if sug_to_update:
                                sug_to_update.status = AISuggestionStatus.send_failed.value
                                sug_to_update.final_message_id = outbound_msg.id
                        await session.commit()
                elif agent_response.decision == AgentDecision.draft_for_human.value:
                    logger.info(
                        f"⚠️ AI requested human review for conversation #{conversation.id} "
                        f"(decision: draft_for_human) — suggestion #{agent_response.ai_suggestion_id} created"
                    )
                elif agent_response.decision == AgentDecision.handoff.value:
                    logger.info(
                        f"🔄 AI requested human handoff for conversation #{conversation.id}"
                    )
                    conversation.mode = ConversationMode.manual.value
                    await session.commit()
                    if agent_response.answer:
                        await outbound_service.send_message(
                            session=session,
                            conversation_id=conversation.id,
                            content=agent_response.answer,
                            recipient=parsed.reply_recipient,
                            actor=MessageActor.bot.value,
                            origin=MessageOrigin.ai_auto.value,
                            ai_run_id=agent_response.ai_run_id,
                            tokens_used=agent_response.tokens,
                            model=agent_response.model,
                            prompt_version=agent_response.prompt_version,
                        )

            except Exception as e:
                logger.error(f"❌ Pipeline error: {e}", exc_info=True)
                await session.rollback()
            finally:
                runtime_metrics.observe_latency(
                    "message.processing",
                    time.perf_counter() - started,
                )

    def _store_attachments(self, session: AsyncSession, message: Message, envelope) -> None:
        if not envelope.data_message or not envelope.data_message.attachments:
            return
        for att in envelope.data_message.attachments:
            att_rec = MessageAttachment(
                message_id=message.id,
                external_attachment_id=att.id,
                filename=att.filename or f"attachment_{att.id}",
                mime_type=att.content_type,
                size=att.size,
            )
            session.add(att_rec)

    async def _store_inbound_message(
        self,
        session: AsyncSession,
        conversation: Conversation,
        parsed: ParsedMessage,
        *,
        user: User | None = None,
        content: str | None = None,
        signal_event_id: str | None = None,
    ) -> Message:
        """Store an inbound user message. Raises IntegrityError if duplicate."""
        msg = Message(
            conversation_id=conversation.id,
            role="user",
            direction=MessageDirection.inbound.value,
            actor=MessageActor.customer.value,
            content=content or parsed.text,
            sender_id=parsed.sender_id,
            sender_user_id=user.id if user else None,
            sender_name=parsed.sender_name,
            signal_timestamp_ms=parsed.timestamp or None,
            signal_event_id=signal_event_id,
            delivery_status=None,
            origin=MessageOrigin.customer.value,
            occurred_at=datetime.fromtimestamp(parsed.timestamp / 1000)
            if parsed.timestamp
            else utc_now(),
            timestamp=utc_now(),
        )
        session.add(msg)
        await session.flush()
        return msg

    async def _upsert_user(self, session: AsyncSession, parsed: ParsedMessage) -> User:
        """Find existing user by phone/UUID/alias, or create new one with identity."""
        # 1. Lookup by signal_id
        result = await session.execute(select(User).where(User.signal_id == parsed.sender_id))
        user = result.scalar_one_or_none()

        if user is None:
            # 2. Check UserIdentity table
            id_res = await session.execute(
                select(UserIdentity).where(UserIdentity.identity_value == parsed.sender_id)
            )
            ui = id_res.scalar_one_or_none()
            if ui:
                user = await session.get(User, ui.user_id)

        if user is None:
            is_phone = parsed.sender_id.startswith("+")
            user = User(
                signal_id=parsed.sender_id,
                phone_number=parsed.sender_id if is_phone else None,
                signal_uuid=parsed.sender_id if not is_phone else None,
                display_name=parsed.sender_name,
                language=settings.bot_default_language,
            )
            session.add(user)
            await session.flush()

            identity = UserIdentity(
                user_id=user.id,
                identity_type="phone" if is_phone else "uuid",
                identity_value=parsed.sender_id,
            )
            session.add(identity)
            await session.flush()
            logger.info(f"👤 New user created: {parsed.sender_name} ({parsed.sender_id})")
        else:
            user.last_seen = utc_now()
            if parsed.sender_name and parsed.sender_name != user.display_name:
                user.display_name = parsed.sender_name

        return user

    async def _upsert_group_and_member(
        self, session: AsyncSession, parsed: ParsedMessage, user: User
    ) -> tuple[Group, GroupMember]:
        """Find or register Group and update GroupMember roster."""
        res_g = await session.execute(select(Group).where(Group.group_id == parsed.group_id))
        group = res_g.scalar_one_or_none()
        if group is None:
            group = Group(
                group_id=parsed.group_id,
                name=f"Group {parsed.group_id[:8]}...",
                is_active=True,
                sync_status="not_synced",
            )
            session.add(group)
            await session.flush()
            logger.info(f"👥 New group registered: {group.group_id}")
        else:
            group.last_activity = utc_now()

        # Update or create GroupMember
        res_m = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.external_identifier == parsed.sender_id,
            )
        )
        member = res_m.scalar_one_or_none()
        if member is None:
            member = GroupMember(
                group_id=group.id,
                user_id=user.id,
                external_identifier=parsed.sender_id,
                is_admin=False,
                role="member",
                last_seen_at=utc_now(),
            )
            session.add(member)
            await session.flush()
        else:
            member.last_seen_at = utc_now()
            if member.user_id is None and user.id:
                member.user_id = user.id

        return group, member

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        user: User,
        parsed: ParsedMessage,
    ) -> Conversation:
        """Find active conversation or create one (type='dm' or 'group')."""
        query = select(Conversation).where(Conversation.is_active == True)  # noqa: E712

        if parsed.is_group:
            query = query.where(Conversation.group_id == parsed.group_id)
        else:
            query = query.where(
                (Conversation.dm_user_id == user.id)
                | ((Conversation.user_id == user.id) & (Conversation.group_id == None))  # noqa: E711
            )

        query = query.order_by(Conversation.updated_at.desc()).limit(1)
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                type=ConversationType.group.value if parsed.is_group else ConversationType.dm.value,
                user_id=None if parsed.is_group else user.id,
                dm_user_id=None if parsed.is_group else user.id,
                signal_id=f"group.{parsed.group_id}" if parsed.is_group else user.signal_id,
                group_id=parsed.group_id if parsed.is_group else None,
                mode=ConversationMode.auto.value,
                message_count=0,
                is_active=True,
            )
            session.add(conversation)
            await session.flush()
            logger.info(
                f"💬 New conversation #{conversation.id} created (type={conversation.type})"
            )

        return conversation

    async def _generate_fallback_menu(self, session: AsyncSession) -> str:
        """Generate a simple text menu of active products when AI is disabled."""
        result = await session.execute(select(Product).where(Product.is_active == True))  # noqa: E712
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

    async def _send_outbound_reply(
        self,
        session: AsyncSession,
        conversation: Conversation,
        reply_text: str,
        recipient: str,
        reply_to_id: int | None = None,
        tokens_used: int | None = None,
    ) -> Message | None:
        """Send outbound reply with state transitions (pending -> sent/failed)."""
        msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            direction=MessageDirection.outbound.value,
            actor=MessageActor.bot.value,
            sender_id=settings.signal_phone_number or "bot",
            content=reply_text,
            tokens_used=tokens_used,
            reply_to_id=reply_to_id,
            delivery_status=MessageDeliveryStatus.pending.value,
            delivery_error=None,
        )
        session.add(msg)
        await session.flush()

        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.last_message_at = utc_now()

        success = False
        try:
            success = await signal_client.send_reply(recipient, reply_text)
        except Exception as e:
            logger.error(f"❌ Error sending reply: {e}", exc_info=True)
            success = False

        if success:
            msg.delivery_status = MessageDeliveryStatus.sent.value
            msg.delivery_error = None
        else:
            msg.delivery_status = MessageDeliveryStatus.failed.value
            msg.delivery_error = "gateway_send_failed"

        await session.commit()
        return msg


# Singleton instance
message_handler = MessageHandler()
