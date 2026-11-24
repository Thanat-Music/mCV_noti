feat: add SSH admin dashboard and isolated multi-user signup

Add per-account workers behind a shared signed LINE webhook, preserving
u1 runtime state while isolating other users' receivers and notification
history.

- Add a loopback-only dashboard with account approval, pause/resume,
  deletion, per-user preferences, saved-state views and audit records.
- Bind LINE users automatically through start and expiring one-time
  signup links; encrypt CourseVille credentials and require approval.
- Serve homework from saved assignments without requesting or waiting
  for a refresh, and make LINE status/help responses easier to read.
- Classify pushes by title suffix with metadata/URL fallbacks; expose
  assignment, material, score, announcement and other preferences.
- Mark the assumed Announcement suffix as unverified.
- Update Pi installation for multi-user mode and HTML assets, and add
  operational documentation plus an LLM handoff diary.

Validation: selected notification/admin checks, Python compilation,
JavaScript syntax and whitespace checks passed. Full pytest, real HTTP/
browser integration and live Pi/LINE multi-user operation remain pending.
