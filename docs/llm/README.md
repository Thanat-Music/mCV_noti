# mCV_noti — LLM handoff index

Last updated: **2026-11-25, Asia/Bangkok**.

This directory is a compact project memory for a future LLM working on this repository. It records implementation state, decisions, evidence and unfinished work. It is not a claim that local code is deployed, and it does not authorize live sends or deployment by itself.

## Read first

1. Run `git status --short` and `git log -5 --oneline` to establish the current checkout. This index is a dated snapshot, not a live Git status.
2. Read the latest dated diary entry: [2026-11-25](2026-11-25.md).
3. Read [admin operations](../admin.md) for the intended multi-user deployment and [notification behaviour](../notifications.md) for command semantics.
4. Read the actual source before changing behaviour; it is authoritative when documentation and code differ.

## State at handoff

| Item | Recorded state |
| --- | --- |
| Working branch | `cleanup/pi-service` |
| Last observed commit | `5fd2f2a` — Restore Flex cards and add homework and notification settings |
| New multi-user/admin work | Local modifications and new files; not committed or pushed by this session |
| Pi deployment | User supplied logs and real payloads from the Pi; deployment of the new multi-user/admin code is not verified |
| Tests | Selected notification and admin checks passed directly; full pytest, real HTTP/browser integration and live multi-user operation remain unverified |
| Commit draft | [COMMIT_MESSAGE.md](COMMIT_MESSAGE.md) |

## Current user decisions

- Each user has their own CourseVille account and LINE identity. One bot/channel is shared.
- `homework` must read saved assignments immediately. It must not request or wait for a CourseVille refresh.
- Keep startup, incoming-push, daily refresh and failure retries. Notification filtering must not disable reconciliation.
- Homework range is Bangkok midnight today through the end of the day seven calendar days ahead; it includes submitted assignments in that interval and excludes items with no deadline.
- Classify incoming push primarily by the final title suffix. Assignment, Material and Score are confirmed; Announcement is an explicitly marked assumption.
- Admin dashboard is accessed from a notebook via SSH forwarding, not through the public webhook tunnel.
- New users send `start`; the system gets their LINE UID from the signed event and sends a one-time signup link. They enter their own CourseVille credentials and wait for admin approval.
- Preserve the original burgundy Flex cards. Keep LINE text responses spaced and readable. The help footer is `Contact dev for account setup.`

## Source map

| File | Role |
| --- | --- |
| `mcv_service/__main__.py` | Existing account worker, CLI, optional multi-user supervisor |
| `mcv_service/supervisor.py` | Isolated worker lifecycle, shared callback routing, signup delivery loop |
| `mcv_service/accounts.py` | Encrypted account registry, approval, revisions, deletion, audit |
| `mcv_service/enrollment.py` | Sender-bound expiring signup links and durable signup replies |
| `mcv_service/admin.py` | Separate loopback-only admin listener/API and request guards |
| `mcv_service/admin.html` | Dashboard UI, account actions, preferences and saved-state views |
| `mcv_service/dashboard.py` | Read-only, selected-field per-user snapshots |
| `mcv_service/engine.py` | Assignments, reminder/outbox state, cache-only homework, push forwarding |
| `mcv_service/push_types.py` | Title-suffix-first classification and fallback rules |
| `mcv_service/status.py` | Readable stored-state LINE status report |
| `mcv_service/webhook.py` | Signed per-account commands and account-scoped settings tokens |
| `receiver/autopush.py`, `receiver/store.py` | Transport and durable receiver state |
| `deploy/mcv-noti.service`, `scripts/setup-pi.sh` | Intended Pi multi-user activation, code/assets installation |
| `tests/test_admin.py`, `tests/test_notification_features.py` | New feature/isolation checks |

## Next work

1. Review the pending changes, especially lifecycle/shutdown, signup, account deletion and migrations.
2. Install the exact project dependencies in a working Python 3.11+ environment and run full pytest.
3. Run actual HTTP/browser integration and test the dashboard controls; prior checks exercised handlers directly.
4. Commit/push the intended changes, then update the Pi without overwriting its local edits.
5. Verify the existing `u1` subscription/state survives, then run signup/approval and simultaneous operation for an intended second account.
6. Confirm a real announcement payload before removing the unverified label.

## Maintaining this memory

Add a dated entry for a meaningful work session, then update this index's handoff state and next-work list. Keep user decisions, implementation facts, assumptions, test evidence and deployment evidence separate. Never put credentials, private keys, live signup/settings tokens or full sensitive databases in these files. Preserve older dated entries; record corrections as new information.
