feat: wake LINE delivery on commands and redesign notification cards

Wake a dedicated per-account outbox sender immediately when commands are
queued, independently of CourseVille refreshes. Preserve durable dedupe,
retry keys, backoff, dry-run and one-shot behavior.

- Use uniform dark homework cards with small type labels, large course
  names, original assignment fields and functional Detail buttons.
- Add pale notification cards with subtle borders and original links.
- Embed timestamps in cards and remove carousel header spacing gaps.
- Confirm Announcement classification using a genuine Thai payload.
- Add historical previews, a LINE preview sender and a validated u1
  recipient updater that preserves CourseVille credentials.
- Update regression tests, project wiki and Pi upgrade instructions.

Validation: 10 notification checks and focused homework layout checks
passed directly. Mocked delivery wake-up, deduplication and retry checks
passed with a timer-only loop because the host blocks Windows loopback
socket creation. Syntax and whitespace checks passed. Full pytest,
live LINE delivery and Pi deployment remain unverified.
