# Feature Reality Matrix

| Feature | DB | Domain | Backend | Signal | Frontend | Unit | Integration | E2E | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| Bootstrap | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | Initial admin user creation |
| Login / JWT | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | Password hashing + JWT tokens |
| TOTP | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | 2FA verification |
| Signal Gateway | N/A | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL | PARTIAL | NONE | **PARTIAL** | Basic send/groups/about mapped; full contract missing |
| Signal Receive | WORKING | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL | PARTIAL | NONE | **PARTIAL** | WebSocket listener exists, but serial awaiting blocks ingestion |
| Signal Send | WORKING | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | NONE | **PARTIAL** | Basic text send works; attachments/reactions/unified outbound service pending |
| DM | WORKING | PARTIAL | WORKING | WORKING | PARTIAL | WORKING | WORKING | NONE | **PARTIAL** | Direct messages work, but routed via phone string, not conversation entity |
| Groups | WORKING | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | NONE | **PARTIAL** | Basic group sync; members and admins not tracked |
| Contacts | NONE | NONE | PARTIAL | PARTIAL | PARTIAL | NONE | NONE | NONE | **PARTIAL** | Gateway calls exist, not integrated into domain |
| Profile | NONE | NONE | WORKING | WORKING | WORKING | NONE | NONE | NONE | **WORKING** | Fetch and update account profile |
| Devices | NONE | NONE | WORKING | WORKING | WORKING | NONE | NONE | NONE | **WORKING** | List/link devices |
| User Identity | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | NONE | **PARTIAL** | Relies on `signal_id` phone string; UUID/multi-identifier strategy missing |
| Group Members | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Must introduce `GroupMember` model and sync |
| Group Admins | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Part of `GroupMember` domain |
| Group Sync | WORKING | PARTIAL | PARTIAL | WORKING | WORKING | NONE | NONE | NONE | **PARTIAL** | Syncs group entities but not membership roster |
| User Management | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | List, filter, notes, language |
| Blocking | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Block flag suppresses AI |
| User Activity | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL | PARTIAL | PARTIAL | NONE | **PARTIAL** | Currently mixes sender_id vs conversation user_id |
| Conversation | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL | PARTIAL | PARTIAL | NONE | **PARTIAL** | Needs proper `type` (DM/Group), normalized IDs |
| Chat History | WORKING | WORKING | WORKING | N/A | PARTIAL | WORKING | WORKING | NONE | **PARTIAL** | Loads chronological oldest-first; needs latest-first & cursor pagination |
| Unread | NONE | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Needs server-side `last_read_message_id` |
| Manual Takeover | WORKING | PARTIAL | PARTIAL | N/A | WORKING | PARTIAL | PARTIAL | NONE | **PARTIAL** | Mode persisted; race condition during AI generation must be closed |
| AI | WORKING | PARTIAL | WORKING | N/A | N/A | WORKING | WORKING | NONE | **PARTIAL** | Generates responses; lacks structured per-call `AIResponse` object |
| AI Context | WORKING | WORKING | WORKING | N/A | N/A | WORKING | WORKING | NONE | **WORKING** | Deduplicates current message; formats group sender names |
| Summary | PARTIAL | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Column exists in DB, but no trigger/generation logic exists |
| Attachments | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Inbound attachments dropped/ignored; no persistence |
| Reactions | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Filtered out if dataMessage has no text; must be parsed and stored |
| Receipts | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Delivery receipts not processed |
| Remote Delete | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Delete sync events ignored |
| Typing | NONE | NONE | PARTIAL | PARTIAL | NONE | NONE | NONE | NONE | **PARTIAL** | Gateway client has methods, not integrated in pipeline |
| Products | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | CRUD operations working |
| Orders | WORKING | MODEL_ONLY | MODEL_ONLY | N/A | NONE | NONE | NONE | NONE | **MODEL_ONLY** | Skeleton models in DB, no business workflow |
| Payments | WORKING | MODEL_ONLY | MODEL_ONLY | N/A | NONE | NONE | NONE | NONE | **MODEL_ONLY** | Skeleton models in DB, no gateway integration |
| Campaign Broadcast | WORKING | WORKING | WORKING | WORKING | WORKING | NONE | NONE | NONE | **WORKING** | Manual broadcast to groups works |
| Scheduling | NONE | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Honest status: broadcast only, no automated scheduling |
| Audit | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Records key administrative actions |
| Retention | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Data cleanup service |
| Metrics | NONE | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Needs structured runtime metrics |
| Settings | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **PARTIAL** | Monolithic page; needs modular sections |
| Health | WORKING | PARTIAL | PARTIAL | PARTIAL | N/A | NONE | NONE | NONE | **PARTIAL** | Basic `/health`; needs `/health/live` and `/health/ready` |
| Migration | BROKEN | PARTIAL | PARTIAL | N/A | N/A | NONE | NONE | NONE | **BROKEN** | Fresh DB fails on `a0c4522143d4`; needs baseline migration |
| Backup | WORKING | WORKING | WORKING | N/A | N/A | NONE | NONE | NONE | **WORKING** | Backup scripts and protected directory |
| Docker | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **PARTIAL** | Dockerfile exists; needs full smoke validation |
| CI | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL | PARTIAL | NONE | NONE | **PARTIAL** | Runs backend pytest/ruff; needs migration tests and frontend tests |
| Admin UI | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **PARTIAL** | Functional UI; needs Inbox rebuild, design system unification |
