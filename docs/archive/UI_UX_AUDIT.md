# Signal Market Bot — UI/UX Audit & Design System Verification

## 1. Audit Scope & Viewports

This audit evaluates the updated Admin Dashboard across key viewports:
- **Desktop**: 1440 × 900 px
- **Tablet**: 1024 × 768 px
- **Mobile**: 390 × 844 px (iPhone 14)

---

## 2. Page-by-Page Audit Findings

### 2.1 Admin Inbox (`/inbox`)
- **Visual Hierarchy**: Clean split-pane layout. Left pane features search, filters (Type: All/DM/Group; Mode: Auto/Manual/Paused; Unread toggle), and conversation items. Right pane hosts conversation header, chronological message bubble stream, and fixed bottom composer.
- **Responsive Behavior**:
  - *1440×900*: Full dual-pane view with sliding details drawer. Smooth upward scroll for historical cursor pagination.
  - *1024×768*: Sidebar collapses to 20rem; timeline retains comfortable chat bubbles with wrapping.
  - *390×844*: Clean vertical stacking; conversation list provides full touch target size (minimum 44×44px per item).
- **Empty & Loading States**:
  - Unselected state renders informative icon and instructional helper text.
  - Spinner overlays during initial fetch; optimistic pending bubble during send.
- **Accessibility & Focus**:
  - Composer supports `Enter` to submit and `Shift+Enter` for newline.
  - `aria-label="Takeover mode"` on mode selector.
  - High-contrast badges for Auto (green), Manual (amber), and Paused (zinc).

### 2.2 Devices & Account (`/devices`)
- **Fault Isolation**: Replaced previous `Promise.all` with independent `loadProfile()` and `loadDevices()` async lifecycles. If the gateway device endpoint fails, the profile form remains interactive.
- **Date Formatting**: Epoch seconds and milliseconds are normalized automatically; no raw timestamps exposed.
- **Destructive Actions**: Device unlinking requires explicit confirmation dialog before dispatching `DELETE /account/devices/{id}`.

### 2.3 Settings (`/settings`)
- **Modular Tab Architecture**: Replaced previous 900-line continuous scroll page with 7 distinct tabs:
  - `General`: Bot name, default language, market order toggle, prompt template.
  - `Signal Gateway`: REST URL, bot phone number, masked token, connection test.
  - `AI Engine`: Base URL, masked API key, model selector, temperature/tokens sliders, probe & verify buttons.
  - `Campaigns`: Broadcast frequency, quiet hours, group blacklist.
  - `Security & Audit`: Security policy hints, recent administrative audit log table.
  - `Data & Retention`: Message retention threshold, immediate pruning action, rollback.
  - `Diagnostics`: Signal connection status, AI model provider detection, latency.
- **Secret Masking**: Passwords and API tokens display current masked values (`sk-***`, `tok_***`) and never reveal raw secrets in the DOM.

### 2.4 Groups Management (`/groups`)
- **Signal Roster Synchronization**: Sync button pulls authoritative group data from Signal REST daemon, upserting local DB rows and populating `group_members` with admin flags.
- **Member Inspection**: Modal drawer allows reviewing group members, external identifiers, and roles.

### 2.5 Users Management (`/users`)
- **Activity Attribution**: Message counts are calculated based on `Message.sender_user_id`, accurately attributing group and DM messages to the actual sending user.
- **Blocking**: Block/unblock actions feature clear color-coded indicators.

---

## 3. Design System & Component Library

The UI adheres to a unified DaisyUI + Tailwind semantic system:
- `components/ui/Button.tsx`: Variants (`primary`, `secondary`, `danger`, `ghost`), loading spinners, disabled states.
- `components/ui/Badge.tsx`: `ModeBadge` (`Auto`, `Manual`, `Paused`), `DeliveryBadge` (`Sent`, `Delivered`, `Read`, `Pending`, `Failed`).
- `components/ui/Card.tsx`: Standardized card containers with header titles, subtitles, and header actions.
- `components/ui/Modal.tsx`: Focus management and ESC key listener.
