# Private dashboard and multi-user administration

The multi-user runtime serves two separate listeners:

| Port | Purpose | Access |
| --- | --- | --- |
| 8080 | Signed LINE callback, per-user settings and one-time signup | Existing Cloudflare tunnel |
| 8081 | Dashboard and admin API | Loopback only, through SSH forwarding |

The installer enables `--multi-user --admin-port 8081`. For a manual launch, add these flags to the existing `python -m mcv_service` command. Keep all database/key/LINE arguments from your existing deployment. Real delivery still requires `--send`; otherwise signup replies and notifications remain queued.

## Open from your notebook

After installing and activating the updated code on the Pi, run this on the notebook and keep the SSH session open:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 8081:127.0.0.1:8081 music@M103
```

Replace `M103` with the Pi IP/name if needed. Open [http://localhost:8081](http://localhost:8081) on the notebook. If that local port is occupied, forward `18081:127.0.0.1:8081` instead and open `http://localhost:18081`.

SSH authenticates the admin. There is no separate admin password. The admin listener is fixed to 127.0.0.1, checks loopback Host headers and requires an anti-CSRF header for mutations. Do not point a public tunnel or reverse proxy at port 8081. Local processes on the Pi and clients of an intentionally shared SSH forwarding session are within the admin trust boundary. Closing SSH removes notebook access; the service continues running.

## Register users without asking for LINE UID

1. User adds the existing LINE bot as a friend and sends `start` in direct chat.
2. The signed webhook obtains their LINE user ID automatically. A private signup link is queued to that same recipient, with persistent LINE retry keys.
3. The link expires in 15 minutes, is tied to that LINE identity, and can be submitted once. A fresh `start` revokes older unused links; duplicate webhook delivery does not create duplicate messages. Up to three fresh links per minute per LINE identity are allowed.
4. User enters display name and their own CourseVille username/password in the HTTPS signup page. The page never accepts a LINE UID from the browser. Credentials are encrypted using the existing RSA key scheme. The operator controls the private key; encryption at rest does not hide credentials from the operator.
5. User appears as **awaiting approval**. Admin reviews and selects **Approve**. Only then does an isolated worker start and log in. Approval does not itself prove the CourseVille credentials are valid; view the first update result.

A pending user's `start` reports that approval is pending. An approved but paused user's `start` asks them to contact dev. A registered active user's normal commands remain `homework`, `status`, and `settings`. Unknown users cannot access another account's commands or settings. Expired links require a new `start`. The Cloudflare URL may change on restart; request a fresh link if an old URL stops working.

## Dashboard controls

- Overview: user count, pending approvals, live local worker count, failed LINE deliveries and delivery mode.
- Accounts: add manually using an already-known LINE user ID, edit name/password or LINE binding, approve, pause/resume, delete. To change the CourseVille identity itself, create a new user so cached data from another account cannot carry over.
- Per-user view: last successful assignment update, refresh failure marker, last incoming push, assignments due today through +7 days or all saved assignments, recent push types and delivery states.
- Notification preferences: change categories independently for each user, including the marked unverified announcement suffix.
- Request CourseVille update: explicit manual refresh, obeying normal rate/backoff rules. Page refreshes only read saved state.
- Admin activity: recent account, preference and manual-update actions; credential values are never included.

The page rereads saved state every 15 seconds while visible. It never triggers CourseVille requests automatically. Assignment tables show up to 300 saved items; push/delivery tables show the latest 30 retained records. Failed deliveries are visible for diagnosis; this version has no bulk resend button. Push previews show title/course/type, not raw payloads or token URLs. Worker state is local; timestamps cannot guarantee external network connectivity.

Deleting an account stops the worker and removes the saved CourseVille credentials and active recipient mapping. Isolated runtime databases and notification history remain on disk for inspection; deletion is not a data erasure operation. Pausing retains everything and stops that user's worker; pending work can resume on enable, subject to existing expiry and eligibility checks. Existing signup links expire independently.

## Isolation and migration

`u1` retains the existing runtime database and receiver identity. Other accounts use `users/<internal-user-id>.db` beside the main runtime database. Each has its own push subscription, assignments, reminder history, preferences, LINE dedupe and retry state. The registry and encrypted account rows remain in the existing legacy database. Existing non-primary legacy accounts are imported paused, to avoid activating unreviewed recipients. Notification settings links use account-specific paths and signatures, and cannot be used for a different account.

One bot/channel token and one public `/callback` are shared. Callback dispatch uses the sender's authenticated LINE user ID. Do not run the old single-user service alongside the multi-user supervisor against the same state. The installer stops the old service before switching releases. Database migrations add admin tables; existing assignment and receiver tables are preserved.

## Upgrade

After committing/pushing the updated source and pulling it on the Pi:

```bash
sudo bash scripts/setup-pi.sh --install
sudo bash scripts/setup-pi.sh --activate
systemctl status mcv-noti mcv-tunnel
sudo journalctl --namespace=mcv-noti -u mcv-noti -u mcv-tunnel -n 80 -o cat --no-pager
```

Wait for `line.ingress_ready`, open the SSH dashboard, and check that the existing user's worker and assignment snapshot are present. Test signup with an intended additional account and approve it in admin. Real signup delivery, CourseVille login and multi-account operation still require verification on the Pi.
