# Feature Reality Matrix (Round 2 Verified)

| Feature | DB | Domain | Backend | Signal | Frontend | Unit | Integration | E2E | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| Bootstrap | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | Initial admin user creation |
| Login / JWT | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | Password hashing + JWT tokens |
| TOTP | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | PARTIAL | **WORKING** | 2FA verification |
| Signal Gateway | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Verified via FakeSignalGateway and contract suites |
| Signal Receive | WORKING | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Bounded queue (1000), 4 workers, partition locks |
| Signal Send | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | OutboundMessageService: pending -> sent/failed + retry |
| DM | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Discrete DM conversation entity, unified user identity |
| Groups | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | No single conversation owner; senders mapped to messages |
| Contacts | NONE | NONE | PARTIAL | PARTIAL | PARTIAL | NONE | NONE | NONE | **PARTIAL** | Gateway calls exist, not integrated into domain |
| Profile | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Fetch and update account profile with isolated UI load |
| Devices | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | List/unlink devices with independent error boundary |
| User Identity | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | `user_identities` table maps phones & UUIDs to canonical user |
| Group Members | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | `group_members` table and roster synchronization |
| Group Admins | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | `is_admin` flag on GroupMember, sync endpoint |
| Group Sync | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Gateway pull upserts groups and roster |
| User Management | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | List, filter, notes, language |
| Blocking | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Block flag suppresses AI; messages recorded for audit |
| User Activity | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Activity calculated from `Message.sender_user_id` |
| Conversation | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | REST `/conversations` with integer ID, type, mode |
| Chat History | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Chronological timeline, latest-first load, cursor pagination |
| Unread | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Server-side `conversation_read_states`, persisted on read |
| Manual Takeover | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Mid-generation race check closes leak; UI switcher |
| AI | WORKING | WORKING | WORKING | N/A | N/A | WORKING | WORKING | NONE | **WORKING** | Generates responses; token accounting & model fallback |
| AI Context | WORKING | WORKING | WORKING | N/A | N/A | WORKING | WORKING | NONE | **WORKING** | Deduplicates current message; formats group sender names |
| Summary | PARTIAL | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Honest status: column exists, long-term memory not implemented |
| Attachments | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Attachment-only events stored in `message_attachments` & rendered |
| Reactions | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | WORKING | BLOCKED_EXT | **WORKING** | Reaction events parsed, stored in `message_reactions`, displayed |
| Receipts | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Delivery receipts not processed |
| Remote Delete | NONE | NONE | NONE | PARTIAL | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Delete sync events ignored |
| Typing | NONE | NONE | PARTIAL | PARTIAL | NONE | NONE | NONE | NONE | **PARTIAL** | Gateway client has methods, not integrated in pipeline |
| Products | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Full CRUD operations working |
| Orders | WORKING | MODEL_ONLY | MODEL_ONLY | N/A | NONE | NONE | NONE | NONE | **MODEL_ONLY** | Skeleton models in DB, no business workflow |
| Payments | WORKING | MODEL_ONLY | MODEL_ONLY | N/A | NONE | NONE | NONE | NONE | **MODEL_ONLY** | Skeleton models in DB, no gateway integration |
| Campaign Broadcast | WORKING | WORKING | WORKING | WORKING | WORKING | NONE | NONE | NONE | **WORKING** | Manual broadcast to groups works |
| Scheduling | NONE | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Honest status: broadcast only, no automated scheduling |
| Audit | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Records key administrative actions |
| Retention | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Data cleanup service with retention days |
| Metrics | NONE | NONE | NONE | N/A | NONE | NONE | NONE | NONE | **NOT_IMPLEMENTED** | Needs structured runtime metrics export |
| Settings | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Modular 7 tabs, secret masking, connection probing |
| Health | WORKING | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | NONE | **WORKING** | Split `/health/live` and `/health/ready` (checks migration head) |
| Migration | WORKING | WORKING | WORKING | N/A | N/A | WORKING | WORKING | NONE | **WORKING** | Continuous chain (`112aa6e29383 -> c8927140f12a`), fresh & legacy tests |
| Backup | WORKING | WORKING | WORKING | N/A | N/A | NONE | NONE | NONE | **WORKING** | Integrity check + timestamped backup in `data/backups` |
| Docker | WORKING | WORKING | WORKING | N/A | WORKING | NONE | NONE | NONE | **WORKING** | Validated via `docker compose config` |
| CI | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Full quality gate: backend lint/format/pytest/migrations, frontend lint/tsc/test/build |
| Admin UI | WORKING | WORKING | WORKING | N/A | WORKING | WORKING | WORKING | NONE | **WORKING** | Modern `/inbox`, unified DaisyUI design system, test suite |
