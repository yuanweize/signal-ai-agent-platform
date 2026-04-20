"""
Pydantic schemas for Signal API message formats.

Models the JSON structures used by signal-cli-rest-api for:
- Incoming messages (envelope from WebSocket / GET /v1/receive)
- Outgoing messages (POST /v2/send)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ============================================================
# Incoming Message Schemas (from signal-cli-rest-api)
# ============================================================


class SignalGroupInfo(BaseModel):
    """Group metadata in an incoming message."""

    group_id: str = Field(alias="groupId", default="")
    type: str = "DELIVER"  # DELIVER, UPDATE, QUIT, etc.


class SignalDataMessage(BaseModel):
    """Core message content within an envelope."""

    timestamp: int = 0
    message: str | None = None
    expires_in_seconds: int = Field(alias="expiresInSeconds", default=0)
    view_once: bool = Field(alias="viewOnce", default=False)
    group_info: SignalGroupInfo | None = Field(alias="groupInfo", default=None)

    model_config = {"populate_by_name": True}


class SignalReceipt(BaseModel):
    """Read/delivery receipt."""

    type: str = ""  # "READ", "DELIVERY"
    timestamps: list[int] = []


class SignalTypingMessage(BaseModel):
    """Typing indicator."""

    action: str = ""  # "STARTED", "STOPPED"
    timestamp: int = 0
    group_id: str | None = Field(alias="groupId", default=None)

    model_config = {"populate_by_name": True}


class SignalEnvelope(BaseModel):
    """
    Top-level envelope wrapping a Signal message.

    The envelope can contain different types of content:
    - dataMessage: Regular text/media message
    - receiptMessage: Read/delivery receipts
    - typingMessage: Typing indicators
    - syncMessage: Multi-device sync (usually ignored)
    """

    source: str = ""  # Sender phone number
    source_number: str | None = Field(alias="sourceNumber", default=None)
    source_uuid: str | None = Field(alias="sourceUuid", default=None)
    source_name: str | None = Field(alias="sourceName", default=None)
    source_device: int = Field(alias="sourceDevice", default=1)
    timestamp: int = 0

    data_message: SignalDataMessage | None = Field(alias="dataMessage", default=None)
    receipt_message: SignalReceipt | None = Field(alias="receiptMessage", default=None)
    typing_message: SignalTypingMessage | None = Field(alias="typingMessage", default=None)

    model_config = {"populate_by_name": True}

    @property
    def sender_id(self) -> str:
        """Best available sender identifier (number or UUID)."""
        return self.source_number or self.source or self.source_uuid or ""

    @property
    def sender_name(self) -> str:
        """Sender display name with fallback."""
        return self.source_name or self.sender_id

    @property
    def is_data_message(self) -> bool:
        """True if this envelope contains an actual text message."""
        return self.data_message is not None and self.data_message.message is not None

    @property
    def is_group_message(self) -> bool:
        """True if this message was sent in a group."""
        return (
            self.data_message is not None
            and self.data_message.group_info is not None
            and bool(self.data_message.group_info.group_id)
        )

    @property
    def group_id(self) -> str | None:
        """Group ID if this is a group message, else None."""
        if self.is_group_message:
            return self.data_message.group_info.group_id
        return None

    @property
    def text(self) -> str | None:
        """Message text content."""
        if self.data_message:
            return self.data_message.message
        return None


class SignalIncomingMessage(BaseModel):
    """
    Root model for messages received from signal-cli-rest-api.

    WebSocket and polling both return this structure.
    """

    envelope: SignalEnvelope
    account: str = ""  # The bot's own number

    model_config = {"populate_by_name": True}


# ============================================================
# Outgoing Message Schemas (POST /v2/send)
# ============================================================


class SignalSendRequest(BaseModel):
    """Request body for POST /v2/send."""

    message: str
    number: str  # Bot's own registered number
    recipients: list[str]  # Phone numbers or "group.{groupId}" prefixed IDs
    text_mode: str | None = None  # "normal" or "styled"


class SignalSendResponse(BaseModel):
    """Response from POST /v2/send (partial — only fields we care about)."""

    timestamp: str | None = None
    results: list[dict] | None = None


# ============================================================
# Internal message representation (for passing between services)
# ============================================================


class ParsedMessage(BaseModel):
    """
    Cleaned, normalized message for internal processing.

    Created by MessageHandler from a raw SignalEnvelope.
    """

    sender_id: str  # Phone number or UUID
    sender_name: str
    text: str
    group_id: str | None = None  # None = direct message
    timestamp: int = 0
    is_group: bool = False

    @property
    def reply_recipient(self) -> str:
        """
        The recipient to use when replying.

        For group messages: "group.{groupId}"
        For DMs: sender's phone number
        """
        if self.is_group and self.group_id:
            # Ensure group. prefix for sending
            gid = self.group_id
            if not gid.startswith("group."):
                gid = f"group.{gid}"
            return gid
        return self.sender_id
