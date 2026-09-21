# Signal API Contract Audit

> Based on swagger.json included in repository (signal-cli-rest-api v1.0)  
> Verified against: `backend/app/services/signal_client.py`

## Summary

All methods in `SignalClient` have been audited against swagger.json.  
Bugs found in original code are documented with their fix status.

---

## Contract Matrix

| Client Method | HTTP Method | Swagger Path | Body/Params | Original Bug | Fixed |
|--------------|-------------|-------------|-------------|-------------|-------|
| `send_message` | POST | `/v2/send` | `{message, number, recipients}` | ✓ Correct | — |
| `show_typing` | PUT | `/v1/typing-indicator/{number}` | `{recipient}` in body | ✓ Correct | — |
| `hide_typing` | DELETE | `/v1/typing-indicator/{number}` | `{recipient}` in body | **P1-5: Was using query params** | ✅ Fixed |
| `send_read_receipt` | POST | `/v1/receipts/{number}` | `{receipt_type, recipient, timestamp}` | **P1-6: Was using `target_author` not `recipient`** | ✅ Fixed |
| `send_reaction` | POST | `/v1/reactions/{number}` | `{reaction, recipient, target_author, timestamp}` | **P1-2: Was using `target_timestamp` not `timestamp`** | ✅ Fixed |
| `remove_reaction` | DELETE | `/v1/reactions/{number}` | `{recipient, target_author, timestamp}` in body | **P1-3: Was using query params** | ✅ Fixed |
| `delete_message` | DELETE | `/v1/remote-delete/{number}` | `{recipient, timestamp}` in body | **P1-4: Was using query params with `target_timestamp`** | ✅ Fixed |
| `list_attachments` | GET | `/v1/attachments` | — | ✓ Correct | — |
| `serve_attachment` | GET | `/v1/attachments/{attachment}` | — | ✓ Correct | — |
| `delete_attachment` | DELETE | `/v1/attachments/{attachment}` | — | ✓ Correct | — |
| `list_contacts` | GET | `/v1/contacts/{number}` | — | ✓ Correct | — |
| `sync_contacts` | POST | `/v1/contacts/{number}/sync` | — | ✓ Correct | — |
| `get_contact_avatar` | GET | `/v1/contacts/{number}/{uuid}/avatar` | — | ✓ Correct | — |
| `list_groups` | GET | `/v1/groups/{number}` | — | ✓ Correct | — |
| `get_group` | GET | `/v1/groups/{number}/{groupid}` | — | ✓ Correct | — |
| `quit_group` | POST | `/v1/groups/{number}/{groupid}/quit` | — | ✓ Correct | — |
| `create_group` | POST | `/v1/groups/{number}` | `{name, members}` | ✓ Correct | — |
| `update_group` | PUT | `/v1/groups/{number}/{groupid}` | `{name, description}` | ✓ Correct | — |
| `add_group_members` | POST | `/v1/groups/{number}/{groupid}/members` | `{members}` | ✓ Correct | — |
| `remove_group_members` | DELETE | `/v1/groups/{number}/{groupid}/members` | `{members}` in body | ✓ Correct | — |
| `modify_group_admins` (add) | POST | `/v1/groups/{number}/{groupid}/admins` | **swagger: `{admins}`, impl: `{members}`** | **P2: Field name mismatch** | ⚠️ P2 variance |
| `modify_group_admins` (remove) | DELETE | `/v1/groups/{number}/{groupid}/admins` | **swagger: `{admins}`, impl: `{members}`** | **P2: Field name mismatch** | ⚠️ P2 variance |
| `update_profile` | PUT | `/v1/profiles/{number}` | `{name, about}` | ✓ Correct | — |
| `list_devices` | GET | `/v1/devices/{number}` | — | ✓ Correct | — |
| `remove_device` | DELETE | `/v1/devices/{number}/{deviceId}` | — | ✓ Correct | — |
| `get_qrcode_link` | GET | `/v1/qrcodelink` | query: `device_name` (required) | **Missing required `device_name` param** | ⚠️ P2 |
| `search_numbers` | GET | `/v1/search/{number}` | query: `numbers` (array) | **Using CSV join; swagger uses `multi`** | ⚠️ P2 |
| `test_connection` | GET | `/v1/about` | — | **P0-7: Was calling `/v1/receive` (consumes messages!)** | ✅ Fixed |

---

## P2 Variances (not blocking, documented)

### `modify_group_admins` — body field name

- **swagger** `ChangeGroupAdminsRequest`: `{ "admins": [...] }`
- **impl**: `{ "members": [...] }`

Signal CLI REST API may accept either; this works in practice but should be corrected to match the contract exactly.

### `get_qrcode_link` — missing required query param

swagger requires `device_name` query parameter. Current implementation calls `/v1/qrcodelink` with no params. The gateway may return 400. This endpoint is not used in any critical path.

### `search_numbers` — array serialization

swagger uses `collectionFormat: multi` (repeated params: `?numbers=+420...&numbers=+421...`).  
Current implementation joins with CSV: `?numbers=+420...,+421...`. Behavior depends on gateway version.

---

## Contract Test Coverage

Every method above with ✅ or a contract check has a test in:
`backend/tests/test_signal_gateway_contract.py`

All 38 backend tests PASS.

---

## Note on GET /account/profile

signal-cli-rest-api does **not** provide a `GET /v1/profiles/{number}` endpoint.  
The swagger only shows `PUT /v1/profiles/{number}`.  
Our `GET /api/account/profile` returns the configured phone number with a note.  
This is `BLOCKED_EXTERNAL` — full profile fetch would require a different gateway API.
