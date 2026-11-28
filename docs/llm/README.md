# mCV_noti — LLM handoff index

Last updated: **2026-11-28, Asia/Bangkok**.

This directory is a compact project memory for a future LLM working on this repository. It records implementation state, decisions, evidence and unfinished work. It is not a claim that local code is deployed, and it does not authorize live sends or deployment by itself.

## Read first

1. Run `git status --short` and `git log -5 --oneline` to establish the current checkout. This index is a dated snapshot, not a live Git status.
2. Read the latest dated diary entry: [2026-11-28](2026-11-28.md). The [2026-11-25](2026-11-25.md) entry is historical.
3. Read [admin operations](../admin.md) for the intended multi-user deployment and [notification behaviour](../notifications.md) for command semantics.
4. Read the actual source before changing behaviour; it is authoritative when documentation and code differ.

## State at handoff

| Item | Recorded state |
| --- | --- |
| Working branch | `cleanup/pi-service` |
| Last observed commit | `5186e31` - feat: add SSH admin dashboard and isolated multi-user signup |
| Current local work | Event-driven LINE sender, final Flex design, verified Announcement suffix, preview/recipient tools and wiki; not committed/pushed in this session |
| Pi deployment | User supplied logs and real payloads from the Pi; deployment of the new multi-user/admin code is not verified |
| Tests | 10 notification checks and final layout checks passed directly; mocked async delivery tests passed with a timer-only loop. Full pytest and normal-loop/live integration remain unverified |
| Commit draft | [COMMIT_MESSAGE.md](COMMIT_MESSAGE.md) |
| Update commands | [Pi upgrade runbook](../update.md) |

## Current user decisions

- Each user has their own CourseVille account and LINE identity. One bot/channel is shared.
- `homework` must read saved assignments immediately. It must not request or wait for a CourseVille refresh.
- Keep startup, incoming-push, daily refresh and failure retries. Notification filtering must not disable reconciliation.
- Homework range is Bangkok midnight today through the end of the day seven calendar days ahead; it includes submitted assignments in that interval and excludes items with no deadline.
- Classify incoming push primarily by the final title suffix. Assignment, Material, Score and Announcement are all confirmed by genuine payloads.
- Admin dashboard is accessed from a notebook via SSH forwarding, not through the public webhook tunnel.
- New users send `start`; the system gets their LINE UID from the signed event and sends a one-time signup link. They enter their own CourseVille credentials and wait for admin approval.
- Homework uses the original fields and Detail button on a uniform dark card, small type above large course name: HOMEWORK / HOMEWORK DUE / NEW ASSIGNMENT / DEADLINE UPDATED. New and changed work remain homework cards, without bracketed tags. Light notifications use tinted backgrounds and subtle outlines. See the latest diary for exact final design.
- Account commands wake an independent sender immediately; keep durable dedupe, backoff and frozen retry payloads. No CourseVille refresh is requested by homework.
- Incoming Assignment update pushes and snapshot-detected changes are still separate notifications. Proposed cross-source suppression is not implemented.
- Keep LINE text responses readable. The help footer is `Contact dev for account setup.` Rich Menu message actions are start / homework / settings; image upload remains manual.

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
| `mcv_service/delivery.py` | Per-account event-driven sender, independently of CourseVille refresh |
| `mcv_service/flex.py` | Dark homework / pale notification layouts and original content links |
| `mcv_service/push_types.py` | Title-suffix-first classification and fallback rules |
| `mcv_service/status.py` | Readable stored-state LINE status report |
| `mcv_service/webhook.py` | Signed per-account commands and account-scoped settings tokens |
| `receiver/autopush.py`, `receiver/store.py` | Transport and durable receiver state |
| `deploy/mcv-noti.service`, `scripts/setup-pi.sh` | Intended Pi multi-user activation, code/assets installation |
| `tests/test_admin.py`, `tests/test_notification_features.py` | New feature/isolation checks |
| `tests/test_delivery.py` | Wake-up during refresh, dedupe/backoff and homework layout checks |
| `scripts/preview_line.py`, `scripts/notification_samples.json` | Real-send preview using historical sample data |
| `scripts/update_line_user.py` | Validated u1 LINE recipient update; encrypted credentials preserved |

## Next work

1. Run full pytest and normal-event-loop integration with working Python 3.11+ dependencies; this sandbox cannot initialize the normal Windows asyncio loopback socket.
2. Review sender lifecycle/shutdown and verify signed webhook wake-up plus multi-account routing.
3. Commit/push and follow [the upgrade runbook](../update.md), preserving Pi local edits and runtime state.
4. Verify final rendering, Detail/content links and command latency during an actual CourseVille refresh.
5. Upload the English Rich Menu separately if desired; code deployment does not publish the image.

## Maintaining this memory

Add a dated entry for a meaningful work session, then update this index's handoff state and next-work list. Keep user decisions, implementation facts, assumptions, test evidence and deployment evidence separate. Never put credentials, private keys, live signup/settings tokens or full sensitive databases in these files. Preserve older dated entries; record corrections as new information.
