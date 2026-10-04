# mCV Notifier

Personal CourseVille assignment notifications for a Raspberry Pi, delivered through LINE.

## Start here

- [Setup and operations](docs/receiver.md)
- `mcv_service/__main__.py`: application entry point and scheduling
- `mcv_service/engine.py`: assignment changes and reminder rules
- `receiver/courseville.py`: CourseVille subscription and assignment API

## Layout

| Directory | Responsibility |
| --- | --- |
| `receiver/` | Push transport, durable inbox, CourseVille login/API and logging |
| `mcv_service/` | Reminder rules, LINE delivery, webhook and tunnel management |
| `scripts/` | Pi preflight, installation and encrypted account import |
| `deploy/` | systemd services and journal retention settings |
| `tests/` | Automated behaviour and failure-recovery tests |
| `docs/` | Installation, operation and verification instructions |

`database/`, `secret/`, `.env` and `state/` are local private data, not source packages. Existing account files remain usable. The superseded server, notifier, scraper, utility modules and receiver-only installer have been removed.

## Development

Use Python 3.11 or newer:

```bash
python -m venv .venv-noti
# Activate the environment using your shell's activation command.
python -m pip install -r requirements-test.txt
python -m pytest tests -q
python -m receiver proof
python -m mcv_service --once --no-receiver
```

The application defaults to dry-run; `--send` enables actual LINE delivery. Dry-run still writes runtime state and queues messages, so use a separate database for experiments. The Pi installer is `scripts/setup-pi.sh`; see the runbook before activation.

CourseVille registration and controlled push transport have been tested. Genuine CourseVille push delivery and continuous operation on the Pi still need verification. The admin dashboard remains deferred.
