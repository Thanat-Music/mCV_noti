# Personal Pi notification service

The new entry point is `python -m mcv_service`. One account (`u1`), one recipient, no Firebase, no backups. Admin dashboard is deferred until live operation is verified.

## Flow and schedule

CourseVille publishes encrypted Web Push to a Mozilla Autopush subscription. Our outbound WebSocket receiver decrypts and commits an inbox row plus a refresh request before acknowledging receipt. Duplicate transport IDs do not cause duplicate work. The refresher authenticates to CourseVille and retrieves current assignments. SQLite stores assignment generations, reminder thresholds and a persistent LINE outbox.

Startup, received push and the daily 06:00 Asia/Bangkok run fetch assignments. The daily run reconciles submission status and sends due reminders; three-day and one-day thresholds fire once each. Reminders stop at the deadline. New assignments and changed deadlines alert immediately after discovery. Missed edits are caught on the daily fetch. Initial import sends one summary. Cached-data summaries identify the last successful refresh when refresh fails. Downtime catches up only the current day's summary.

LINE delivery uses persistent retry keys. Ambiguous failures retry; possible duplicates remain preferable to lost notifications. Permanent API errors remain visible as failed outbox rows. A separate Cloudflare Quick Tunnel process exposes only the signed LINE callback and health endpoint. Each new tunnel URL is tested, updated through LINE API, read back and verified. Tunnel readiness does not affect outbound CourseVille Web Push.

## Local checks

Use Python 3.11+ from the repository directory:

```powershell
py -3 -m venv .venv-noti
.\.venv-noti\Scripts\python -m pip install -r requirements-test.txt
.\.venv-noti\Scripts\python -m pytest tests -q
.\.venv-noti\Scripts\python -m receiver proof
.\.venv-noti\Scripts\python -m mcv_service --once --no-receiver
```

The last command authenticates using the encrypted u1 database account and writes runtime state, but does not send LINE messages. Use a separate `--database` path for disposable dry runs: dry runs still build the outbox. Do not later activate a disposable test database accidentally.

## Pi installation

Copy the repository to the Pi, excluding virtual environments, caches and credentials. Transfer the existing database, matching private key and LINE environment file separately over SSH. Do not put secrets in Git or chat. The LINE file needs `CHANNEL_ACCESS_TOKEN` and `CHANNEL_SECRET`; the encrypted account row supplies the recipient.

From the Pi checkout:

```bash
bash scripts/setup-pi.sh --check
sudo bash scripts/setup-pi.sh --install
# Replace the three /secure-transfer paths with the files you transferred.
sudo python3 scripts/import_account.py /secure-transfer/main.db /var/lib/mcv-noti/main.db --user u1
sudo chown mcv-noti:mcv-noti /var/lib/mcv-noti/main.db
sudo chmod 0600 /var/lib/mcv-noti/main.db
sudo install -m 0600 /secure-transfer/private_key.pem /etc/mcv-noti/credentials/private_key.pem
sudo install -m 0600 /secure-transfer/line.env /etc/mcv-noti/credentials/line.env
sudo bash scripts/setup-pi.sh --activate
```

Installation downloads dependencies and installs stopped services. Activation enables real LINE delivery, CourseVille registration and the public callback tunnel. Enable webhook use for this LINE channel in LINE Developers if it is not already enabled. Keep the Pi clock synchronized. Do not run another receiver process with the same subscription database.

Upgrades: run `--install` from the updated checkout, then `--activate`. Existing state and credentials are preserved. Old release directories remain; review and remove obsolete releases manually when needed. No backup is created.

## Operations and logging

```bash
systemctl status mcv-noti mcv-tunnel
sudo journalctl --namespace=mcv-noti -u mcv-noti -u mcv-tunnel -f -o cat
sudo -u mcv-noti /opt/mcv-noti/current/.venv/bin/python -m receiver --database /var/lib/mcv-noti/main.db status
sudo systemctl restart mcv-noti
sudo systemctl restart mcv-tunnel
sudo systemctl stop mcv-tunnel mcv-noti
```

Logs are JSON events with allowlisted metadata, not remote exception bodies, credentials or payloads. A bounded 1,024-record queue prevents slow diagnostics from blocking the receiver; overload drops diagnostic records. Journald is capped at 100 MB / 14 days with 1 GB free-space reserve. The durable inbox/outbox is independent of diagnostics. Processed inbox rows expire after seven days and completed outbox rows after 30 days; pending work is retained. Monitor disk usage: retention is not a hard cap on pending data.

Look for `courseville.subscription_verified`, `refresh.completed`, `delivery.accepted` and `line.ingress_ready`. Registration timestamps do not prove current connectivity. Repeated refresh failures require checking account login; failed LINE delivery requires checking channel credentials, recipient and quota. Do not delete runtime state to fix transient errors: it contains subscription keys and reminder history.

## Receiver verification and remaining gates

`python -m receiver proof` creates an isolated temporary channel and verifies encrypted receipt, duplicate suppression, wrong-sender rejection, offline delivery, stable subscription reuse, and redelivery after an omitted acknowledgement. It unregisters the test channel afterward. This proves our receiver against a controlled sender, not CourseVille's sender.

The real u1 subscription was published and confirmed through CourseVille list/check. A live fetch returned seven courses and 32 assignments. A ten-minute listening window contained no genuine CourseVille event, so sender compatibility is still unproven.

For the next genuine course update, record the receiver inbox count before and after, confirm a refresh follows, and compare the resulting assignment data with CourseVille. Material or announcement pushes may trigger a refresh without an assignment alert. Do not edit a real course merely to manufacture a test. Then verify a real LINE notification on the intended personal account. Restart the app and confirm the same subscription is reused; restart the tunnel and confirm LINE's configured URL matches the new callback and a signed webhook succeeds. Run a 72-hour Pi soak including a network outage and restart: pending work must recover, accepted reminder thresholds must not repeat, and expired assignments must produce no reminders.

Automated tests and the controlled live transport proof have passed on Windows. Native ARM installation, systemd service activation, live LINE/tunnel changes, real CourseVille push delivery and the Pi soak are deployment gates, not completed tests. Autopush's external client protocol is experimental; daily reconciliation is the fallback, and immediate delivery is not guaranteed.
