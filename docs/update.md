# Publish and update the Pi

Assumes an already provisioned Pi and branch `cleanup/pi-service`. Run Git commands in the existing checkout. A normal upgrade preserves service state and credentials; do not re-import accounts.

## Commit and push from the development computer

```powershell
git status --short
git diff --check
git add README.md mcv_service/__main__.py mcv_service/delivery.py mcv_service/engine.py mcv_service/flex.py mcv_service/push_types.py mcv_service/webhook.py scripts/notification_samples.json scripts/preview_line.py scripts/update_line_user.py tests/test_delivery.py tests/test_notification_features.py docs/notifications.md docs/update.md docs/llm/README.md docs/llm/2026-11-28.md docs/llm/COMMIT_MESSAGE.md
git diff --cached --stat
git commit -F docs/llm/COMMIT_MESSAGE.md
git push origin cleanup/pi-service
```

Run each step after the previous succeeds. With a working test environment, run `python -m pytest tests -q` before committing. Limited session validation is recorded in the diary; it is not a full suite pass.

## Update the Pi

SSH to the Pi and enter its existing repository folder:

```bash
git status --short
git branch --show-current
```

If there are local edits, inspect and preserve them first. One option is:

```bash
git stash push -u -m "pi-local-before-notification-update"
```

Do not automatically pop this stash over the new code. Review whether older Pi fixes are still needed.

From a clean checkout on `cleanup/pi-service`:

```bash
git pull --ff-only origin cleanup/pi-service
bash scripts/setup-pi.sh --check
sudo bash scripts/setup-pi.sh --install
sudo bash scripts/setup-pi.sh --activate
sudo systemctl status mcv-noti.service mcv-tunnel.service --no-pager
```

Continue only when each command succeeds. `--install` stages a release, stops current services and switches the release link. `--activate` starts actual notifications and the tunnel. No database/credential re-provisioning is needed. Restarting without installation would still run the old release at `/opt/mcv-noti/current`.

## Logs and verification

```bash
sudo journalctl --namespace=mcv-noti -u mcv-noti.service -u mcv-tunnel.service -n 100 --no-pager -o cat
sudo journalctl --namespace=mcv-noti -u mcv-noti.service -u mcv-tunnel.service -f -o cat
```

Send `homework`, `status`, `settings`, `start` from the intended LINE account. Check:

- Cached homework begins delivery without the old five-second polling wait, including during a refresh.
- Dark homework cards show the correct small type, large course, controlled spacing and functional Detail.
- Light notification cards have a subtle border and original content links.
- Announcement is no longer marked unverified in settings.
- `line.ingress_ready`, `refresh.completed`, `delivery.accepted` appear as appropriate. The new tunnel URL must become ready before webhook commands arrive.

Previously frozen pending messages may retain their old design under their retry key. Test a new command; do not delete runtime/outbox state to force a cosmetic refresh.

## Rich menu (manual)

Upload the English image in LINE Official Account Manager, choose three equal horizontal areas, and configure Text actions:

| Position | Label | Message |
| --- | --- | --- |
| Left | GET STARTED | `start` |
| Center | HOMEWORK | `homework` |
| Right | SETTINGS | `settings` |

The generated image is separate from this repository. Updating code does not publish it. Check downloaded image dimensions against the selected template before upload.
