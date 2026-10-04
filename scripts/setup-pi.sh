#!/usr/bin/env bash
# Run --check first. --install stages code; --activate explicitly starts real delivery.
# Does not create backups or overwrite existing credentials/state.
set -Eeuo pipefail
umask 077
mode="${1:---check}"
[[ "$mode" == --check || "$mode" == --install || "$mode" == --activate ]] || {
    echo 'Usage: setup-pi.sh --check|--install|--activate' >&2; exit 2;
}
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$source_dir/scripts/check-pi.sh"
systemd_version="$(systemd --version | awk 'NR==1 {print $2}')"
[[ "$systemd_version" -ge 247 ]] || { echo 'systemd 247+ required for service credentials' >&2; exit 1; }
[[ "$mode" != --check ]] || { echo 'Install will use Cloudflare official apt repository and a Python venv.'; exit 0; }
[[ "$EUID" -eq 0 ]] || { echo 'Run installation/activation with sudo' >&2; exit 1; }
exec 9>/run/mcv-noti-install.lock
flock -n 9 || { echo 'Another installation is running' >&2; exit 1; }
if [[ "$mode" == --install ]]; then
    apt-get update
    apt-get install -y python3-venv ca-certificates curl
    if ! command -v cloudflared >/dev/null; then
        install -d -m 0755 /usr/share/keyrings
        curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
        chmod 0644 /usr/share/keyrings/cloudflare-main.gpg
        printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/mcv-cloudflared.list
        chmod 0644 /etc/apt/sources.list.d/mcv-cloudflared.list
        apt-get update
        apt-get install -y cloudflared
    fi
    id mcv-noti >/dev/null 2>&1 || useradd --system --home-dir /var/lib/mcv-noti --shell /usr/sbin/nologin mcv-noti
    install -d -m 0755 /opt/mcv-noti/releases
    install -d -m 0700 -o mcv-noti -g mcv-noti /var/lib/mcv-noti /var/lib/mcv-noti/tunnel-home
    install -d -m 0700 /etc/mcv-noti/credentials
    digest="$(find "$source_dir/receiver" "$source_dir/mcv_service" "$source_dir/deploy" "$source_dir/requirements.txt" -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)"
    release="/opt/mcv-noti/releases/$digest"
    install -d -m 0755 "$release"
    if [[ ! -f "$release/.ready" ]]; then
        for module in receiver mcv_service; do
            install -d -m 0755 "$release/$module"
            find "$source_dir/$module" -maxdepth 1 -name '*.py' -type f -exec install -m 0644 -t "$release/$module" {} +
        done
        install -m 0644 "$source_dir/requirements.txt" "$release/requirements.txt"
        python3 -m venv "$release/.venv"
        "$release/.venv/bin/python" -m pip install -r "$release/requirements.txt"
        "$release/.venv/bin/python" -m compileall -q "$release/receiver" "$release/mcv_service"
        touch "$release/.ready"
    fi
    # Code and dependencies contain no credentials; the service must read them.
    chmod -R a+rX "$release"
    runuser -u mcv-noti -- "$release/.venv/bin/python" -c 'import aiohttp, websockets, http_ece'
    for unit in mcv-noti mcv-tunnel; do
        install -m 0644 "$source_dir/deploy/$unit.service" "/etc/systemd/system/$unit.service"
    done
    install -d -m 0755 /etc/systemd/journald@mcv-noti.conf.d
    install -m 0644 "$source_dir/deploy/journald-mcv-noti.conf" /etc/systemd/journald@mcv-noti.conf.d/retention.conf
    # Explicit installation, no automatic start. Stop existing services for a consistent switch.
    systemctl stop mcv-tunnel.service mcv-noti.service || true
    ln -sfn "$release" /opt/mcv-noti/current.next
    mv -Tf /opt/mcv-noti/current.next /opt/mcv-noti/current
    systemd-analyze verify /etc/systemd/system/mcv-noti.service /etc/systemd/system/mcv-tunnel.service
    systemctl daemon-reload
    echo 'Code installed. Services stopped. Provision the account as documented, then run --activate.'
    exit 0
fi
test -r /etc/mcv-noti/credentials/private_key.pem
test -r /etc/mcv-noti/credentials/line.env
test -f /var/lib/mcv-noti/main.db
cd /opt/mcv-noti/current
./.venv/bin/python -c "from receiver.courseville import legacy_account; legacy_account('/var/lib/mcv-noti/main.db','/etc/mcv-noti/credentials/private_key.pem','u1'); print('Account decryption verified')"
systemctl disable --now mcv-receiver.service 2>/dev/null || true
systemctl enable --now mcv-noti.service mcv-tunnel.service
echo 'Activated: CourseVille subscription, LINE notifications, and public callback tunnel.'
echo 'Check: journalctl --namespace=mcv-noti -u mcv-noti.service -u mcv-tunnel.service -f -o cat'
