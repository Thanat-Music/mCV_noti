# LINE notifications and preferences

With `--webhook --send` enabled, use these commands in your personal LINE chat. For multiple accounts, use the [SSH admin dashboard and signup guide](admin.md); a new user sends `start` to receive a signup link and waits for admin approval.

| Command | Behaviour |
| --- | --- |
| `homework` | Reads the saved snapshot without requesting or waiting for a refresh, and sends all active assignments due from 00:00 today through 23:59:59 seven calendar days ahead, Asia/Bangkok. Includes submitted and overdue work in that period; excludes work without deadlines. |
| `settings` | Sends a private settings-page link valid for one hour. |
| `status` | Shows a readable stored-state report: update result/last success, assignment count today through +7 days (including submissions), last incoming push, unprocessed pushes and pending/failed LINE deliveries. No refresh or live connectivity probe. |

Assignment alerts and homework use the original burgundy Flex templates, including due date, time left, submission status and Detail button. Cards are split across carousel messages and API requests for large lists. Retry payloads are persisted to keep the same content with each retry key. Commands are handled by the existing signed `/callback`; no second LINE webhook URL is required. Responses use the durable push outbox, so they count toward the channel's push quota.

Homework always reads saved data and shows the last successful update time. It never increments refresh demand or waits for pending refreshes. Without a successful snapshot it reports that data is not yet available. Startup, incoming push, daily refresh and failure-retry rules are unchanged.

Settings are stored in SQLite and survive restarts. Every automatic type is enabled by default: initial summary, new assignment, changed deadline, daily 3-day/1-day reminders, CourseVille assignment/announcement/material/score/other pushes, refresh failures and recovery. Commands always remain available. Disabling a type skips pending and future deliveries; skipped notifications are not replayed when re-enabled. Reminders remain at the existing daily 06:00 Bangkok schedule.

CourseVille pushes have five independent settings: assignments, announcements, learning materials, scores, and other/unrecognized updates. Exact title suffixes take priority: " - Assignment", " - Material", and " - Score" were observed in genuine Pi payloads. **Assumption (unverified): announcements end in " - Announcement".** The announcement checkbox is marked "unverified suffix" until confirmed by a genuine sample. Only the final suffix is matched, never arbitrary words in the title or body.

When no recognized title suffix is present, explicit type/category/event metadata and recognized CourseVille URL paths are fallbacks. Conflicting suffixes (across nested notification objects) or conflicting fallback signals become Other; unknown formats remain Other when no fallback is recognized. Verified routes include q=courseville/course/<course>/assignment/<id> and q=courseville/course/<course>/material/<id>. Score payloads can link only to the course. The message field is the course title; the icon files path is not a type signal.

Existing saved courseville_push preferences become defaults for all five categories, preserving an opt-out. Pending legacy unclassified messages follow Other. Filtering delivery does not stop assignment refreshes. Assignment pushes can also produce a detailed assignment card. This does not poll announcement history or guarantee CourseVille emits every update.

The settings page uses an expiring signed link, then an HttpOnly SameSite cookie and a form token. Keep the link private. Request a new link after expiry or a tunnel URL change. The public tunnel serves `/settings` alongside `/callback` and `/healthz`; access to settings requires the private token. It exposes notification preferences only.

## Pi upgrade

From the updated checkout:

```bash
sudo bash scripts/setup-pi.sh --install
sudo bash scripts/setup-pi.sh --activate
```

The installer includes the restored JSON templates. Then send `homework` and `settings` to the bot and check one enabled/disabled notification type. Existing runtime state and credentials are preserved.
