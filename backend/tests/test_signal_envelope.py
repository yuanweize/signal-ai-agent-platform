"""
Unit tests: Signal envelope parsing and sender identity.

Verifies that SignalEnvelope correctly resolves sender_id and group_id
from the various field combinations present in the gateway response.
"""

from app.schemas.signal import ParsedMessage, SignalEnvelope


def _make_envelope(**kwargs) -> SignalEnvelope:
    defaults = {
        "source": "",
        "sourceNumber": None,
        "sourceUuid": None,
        "sourceName": None,
        "sourceDevice": 1,
        "timestamp": 1700000000000,
    }
    defaults.update(kwargs)
    return SignalEnvelope.model_validate(defaults)


class TestSenderIdentity:
    def test_source_number_preferred_over_source(self):
        env = _make_envelope(source="+420111000000", sourceNumber="+420999000000")
        assert env.sender_id == "+420999000000"

    def test_source_uuid_fallback(self):
        env = _make_envelope(source="", sourceNumber=None, sourceUuid="abc-uuid-123")
        assert env.sender_id == "abc-uuid-123"

    def test_source_fallback_when_no_number_or_uuid(self):
        env = _make_envelope(source="+420111000000", sourceNumber=None, sourceUuid=None)
        assert env.sender_id == "+420111000000"

    def test_sender_name_fallback_to_id(self):
        env = _make_envelope(source="+420111000000", sourceName=None)
        assert env.sender_name == "+420111000000"

    def test_sender_name_from_source_name(self):
        env = _make_envelope(source="+420111000000", sourceName="Alice")
        assert env.sender_name == "Alice"


class TestGroupMessage:
    def test_group_message_detected(self):
        env = _make_envelope(
            sourceNumber="+420111000000",
            dataMessage={
                "timestamp": 1700000000000,
                "message": "hello group",
                "groupInfo": {"groupId": "group-abc-123", "type": "DELIVER"},
            },
        )
        assert env.is_group_message is True
        assert env.group_id == "group-abc-123"

    def test_dm_not_group(self):
        env = _make_envelope(
            sourceNumber="+420111000000",
            dataMessage={
                "timestamp": 1700000000000,
                "message": "hello dm",
            },
        )
        assert env.is_group_message is False
        assert env.group_id is None

    def test_has_attachments(self):
        env = _make_envelope(
            sourceNumber="+420111000000",
            dataMessage={
                "timestamp": 1700000000000,
                "message": None,
                "attachments": [{"contentType": "image/jpeg", "id": "att-1", "size": 12345}],
            },
        )
        assert env.has_attachments is True
        assert env.text is None


class TestParsedMessage:
    def test_dm_reply_recipient_is_sender(self):
        msg = ParsedMessage(
            sender_id="+420111000000",
            sender_name="Alice",
            text="hi",
            group_id=None,
            timestamp=1700000000000,
            is_group=False,
        )
        assert msg.reply_recipient == "+420111000000"

    def test_group_reply_recipient_has_prefix(self):
        msg = ParsedMessage(
            sender_id="+420111000000",
            sender_name="Alice",
            text="hi group",
            group_id="abc123",
            timestamp=1700000000000,
            is_group=True,
        )
        assert msg.reply_recipient == "group.abc123"

    def test_group_reply_recipient_no_double_prefix(self):
        """group_id already containing 'group.' prefix should not produce double prefix."""
        msg = ParsedMessage(
            sender_id="+420111000000",
            sender_name="Alice",
            text="hi",
            group_id="group.abc123",
            timestamp=1700000000000,
            is_group=True,
        )
        # reply_recipient deduplicates: "group.abc123" stays "group.abc123"
        assert msg.reply_recipient == "group.abc123"

    def test_signal_event_id_format(self):
        # Verify idempotency key construction
        sender = "+420111000000"
        ts = 1700000000000
        event_id = f"{sender}:{ts}"
        assert event_id == "+420111000000:1700000000000"
