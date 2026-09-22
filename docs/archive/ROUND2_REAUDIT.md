# Round 2 Re-Audit of Previous Claims

| Claim | Code Evidence | Test Evidence | Current Result | Notes |
|---|---|---|---|---|
| AI current message dedup | `ai_engine.py`: context excludes current inbound message | `test_ai_context.py::TestCurrentMessageNotDuplicated` | **VERIFIED** | Prevents duplicate injection of latest user message into context |
| Outbound pending/sent/failed | `message_handler.py`, `Message.delivery_status` | `test_ai_context.py::TestOutboundStatusMachine` | **PARTIAL** | State machine exists in Message model, but not centralized in dedicated `OutboundMessageService`; direct Signal calls still scattered |
| Manual mode persisted | `Conversation.mode` persisted in DB, checked in handler | `test_message_pipeline.py::TestManualTakeover` | **PARTIAL** | Checked before AI starts, but vulnerable to mid-generation race condition (no re-check before send) |
| Blocked user enforcement | `message_handler.py`: suppresses outbound if `user.is_blocked` | `test_message_pipeline.py::TestBlockPolicy` | **VERIFIED** | Message stored, AI outbound suppressed |
| Group conversation `user_id` handling | `conversations.user_id = None` for groups | `test_message_pipeline.py::TestGroupAttribution` | **PARTIAL** | Group conversation no longer owned by first sender, but NO `GroupMember` domain exists to track member/admin roles |
| Inbound dedup | `messages.signal_event_id` unique constraint | `test_message_pipeline.py::TestDeduplication` | **PARTIAL** | Deduplication works at DB insert level, but no bounded ingestion queue/worker architecture exists |
| Signal `/v1/about` health check | `signal_client.py::check_health` calls `/v1/about` | `test_signal_gateway_contract.py::TestConnection` | **VERIFIED** | Correct path `/v1/about` instead of `/v1/receive` |
| Groups schema | `groups.description` added | Model & Alembic | **PARTIAL** | Basic description added, but lacks `GroupMember` relation, `sync_status`, `sync_error`, `campaign_eligible` |
| GET profile | `devices.py::GET /account/profile` | Manual route inspect | **VERIFIED** | Added endpoint calling gateway `/v1/profiles/{account}` |
| CORS hardening | `main.py`: reads `ALLOWED_ORIGINS` | Code inspect | **PARTIAL** | Defaults to `*` if empty; needs strict default |
| Mutation retries | `api.ts`: only retries GET requests | Code inspect | **VERIFIED** | Prevents double-submitting mutations on network glitches |
| AI concurrency token state | `ai_engine.py`: returns token usage | Code inspect | **PARTIAL** | Token usage still partially tied to instance attributes rather than structured per-call `AIResponse` |
| Campaign timezone | `campaigns.py`: uses `zoneinfo.ZoneInfo` | Code inspect | **VERIFIED** | Configured timezone respected |
| Group sync | `groups.py::POST /groups/sync` | Code inspect | **PARTIAL** | Syncs group list, but does not synchronize member lists or admin flags |
| Health reporting | `main.py::GET /health` | Code inspect | **PARTIAL** | Returns db status, but lacks split `/health/live` and `/health/ready` endpoints |
| Alembic migrations | `a0c4522143d4` & `397929583aa5` | Execution on empty DB | **WRONG** | Migration fails on fresh DB because tables are not defined in any migration prior to `a0c4522143d4` |
| README truthfulness | Bilingual READMEs updated | Docs inspect | **PARTIAL** | Better aligned, but still needs tightening on non-implemented features |
| CI | `.github/workflows/ci.yml` | Workflow inspect | **PARTIAL** | Tests backend with pytest/ruff, but does NOT run frontend tests (none existed) or migration tests |
