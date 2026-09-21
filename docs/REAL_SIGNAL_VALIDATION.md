# Signal Market Bot — Real Signal Validation Plan

This checklist outlines the manual end-to-end verification procedures when deploying against a real `signal-cli-rest-api` gateway and active Signal account.

---

## 1. Direct Message Inbound & Outbound

### 1.1 Real DM Receive
- **Prerequisite**: Signal bot registered and linked to `signal-cli-rest-api`; bot phone number configured in Settings.
- **Steps**:
  1. From a personal Signal client (e.g. smartphone), send `"Hello bot"` to the bot's phone number.
  2. Observe backend logs for WebSocket reception and event pipeline dispatch.
  3. Open Admin Dashboard at `/inbox`.
- **Expected Result**:
  - Inbound message appears in `/inbox` under a DM conversation for the sender.
  - Sender is registered in `users` with their phone number and UUID.
  - If AI is enabled and mode is `auto`, AI response is generated.
- **Observed Result**: `BLOCKED_EXTERNAL` (Requires live Signal account credentials). Verified locally via `test_round2_messaging_pipeline.py` with mock gateway.

### 1.2 Real DM Send (Manual Takeover)
- **Prerequisite**: Active conversation open in `/inbox`; mode switched to `manual`.
- **Steps**:
  1. Switch takeover selector to `✋ Manual (Human)`.
  2. Type `"Hello from human admin"` in composer and press `Enter`.
- **Expected Result**:
  - Message appears as outbound with `✓ Sent` status.
  - Remote recipient receives the message from the bot account.
  - No automated AI response interferes.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `test_conversations_api.py` and `InboxPage.test.tsx`.

---

## 2. Group Messaging & Identity Attribution

### 2.1 Group Message Receive & Attribution
- **Prerequisite**: Bot added to a Signal group with members Alice and Bob.
- **Steps**:
  1. Alice sends `"Item inquiry"` in the group.
  2. Bob sends `"Price check"` in the group.
  3. Admin checks `/inbox` and `/users`.
- **Expected Result**:
  - One single Group conversation appears in `/inbox`.
  - Messages display separate sender names: `"Alice"` and `"Bob"`.
  - Group conversation has no individual owner (`user_id = null`, `group_id = "group.xxx"`).
  - Alice's activity count in `/users` increments by 1; Bob's increments by 1.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `test_message_pipeline.py` (`TestGroupAttribution`).

---

## 3. Reactions & Attachments

### 3.1 Inbound Reaction
- **Prerequisite**: Inbound message received in DM or group.
- **Steps**:
  1. From personal client, long-press a bot message and react with 👍.
- **Expected Result**:
  - Event is ingested without being filtered.
  - Stored in `message_reactions` with emoji 👍 and reactor identity.
  - Emoji badge 👍 renders below the message bubble in `/inbox`.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `test_round2_messaging_pipeline.py` (`TestReactionOnlyEvent`).

### 3.2 Inbound Attachment
- **Prerequisite**: Personal client in DM with bot.
- **Steps**:
  1. Send a photo or document attachment (e.g. `invoice.pdf`) without text.
- **Expected Result**:
  - Inbound event is stored as a message in the conversation.
  - Attachment metadata (filename, MIME type, size) is linked in `message_attachments`.
  - Timeline displays attachment card with download / preview link.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `test_round2_messaging_pipeline.py` (`TestAttachmentOnlyEvent`).

---

## 4. Signal Gateway Roster & Account Administration

### 4.1 Group Sync
- **Prerequisite**: Signal account belongs to at least one group.
- **Steps**:
  1. Navigate to `/groups`.
  2. Click `↻ Sync from Signal`.
- **Expected Result**:
  - API issues `GET /v1/groups/{number}` to the gateway.
  - Groups table updates with authoritative names and member counts.
  - `group_members` rows populated with admin flags.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `test_groups_sync.py`.

### 4.2 Linked Devices Management
- **Prerequisite**: Gateway running in multi-device mode.
- **Steps**:
  1. Navigate to `/devices`.
  2. Review linked device list and last-seen timestamps.
- **Expected Result**:
  - Profile and devices load independently.
  - Dates display in local formatted time strings.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via `DevicesPage.test.tsx`.

---

## 5. Gateway Resilience & Reconnection

### 5.1 Daemon Disconnect and Auto-Reconnect
- **Prerequisite**: Bot running connected via WebSocket.
- **Steps**:
  1. Restart the `signal-cli-rest-api` container or drop network connection.
  2. Restore connection after 10 seconds.
- **Expected Result**:
  - WebSocket listener logs connection loss and engages exponential backoff.
  - Automatically reconnects and resumes event queue consumption once daemon returns.
- **Observed Result**: `BLOCKED_EXTERNAL`. Verified locally via listener reconnection loop in `signal_listener.py`.
