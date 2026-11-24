# LINE notifications and preferences

With `--webhook --send` enabled, use these commands in your personal LINE chat:

| Command | Behaviour |
| --- | --- |
| `homework` | Requests an assignment refresh, then sends all active assignments due from 00:00 today through 23:59:59 seven calendar days ahead, Asia/Bangkok. Includes submitted and overdue work in that period; excludes work without deadlines. |
| `settings` | Sends a private settings-page link valid for one hour. |
| `status` | Shows service status and the last successful assignment refresh. |

Assignment alerts and homework use the original burgundy Flex templates, including due date, time left, submission status and Detail button. Cards are split across carousel messages and API requests for large lists. Retry payloads are persisted to keep the same content with each retry key. Commands are handled by the existing signed `/callback`; no second LINE webhook URL is required. Responses use the durable push outbox, so they count toward the channel's push quota.

If the requested refresh fails, homework uses the cached assignments with an explicit last-update label. If there is no successful snapshot, it reports that no cached update is available. Refresh attempts retain the existing backoff, and homework requests expire after one hour.

Settings are stored in SQLite and survive restarts. Every automatic type is enabled by default: initial summary, new assignment, changed deadline, daily 3-day/1-day reminders, all CourseVille push notifications, refresh failures and recovery. Commands always remain available. Disabling a type skips pending and future deliveries; skipped notifications are not replayed when re-enabled. Reminders remain at the existing daily 06:00 Bangkok schedule.

“All CourseVille push notifications” forwards each valid incoming CourseVille Web Push once, including announcement/material updates when CourseVille sends them. It shows available title/body/message text; unrecognized payloads receive a generic course-update message. Assignment changes may therefore produce both a raw CourseVille notification and a detailed assignment card. Turn off this type if you only want assignment cards. This does not poll announcement history or guarantee that CourseVille emits every update.

The settings page uses an expiring signed link, then an HttpOnly SameSite cookie and a form token. Keep the link private. Request a new link after expiry or a tunnel URL change. The public tunnel serves `/settings` alongside `/callback` and `/healthz`; access to settings requires the private token. It exposes notification preferences only.

## Pi upgrade

From the updated checkout:

```bash
sudo bash scripts/setup-pi.sh --install
sudo bash scripts/setup-pi.sh --activate
```

The installer includes the restored JSON templates. Then send `homework` and `settings` to the bot and check one enabled/disabled notification type. Existing runtime state and credentials are preserved.
