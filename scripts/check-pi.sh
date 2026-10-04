#!/usr/bin/env bash
# Read-only checks for the supported Pi environment.
set -Eeuo pipefail
[[ "$(uname -s)" == Linux ]] || { echo 'Linux required' >&2; exit 1; }
[[ "$(uname -m)" == aarch64 ]] || { echo 'This installer targets 64-bit Raspberry Pi OS (aarch64)' >&2; exit 1; }
command -v systemctl >/dev/null
command -v python3 >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
version="$(systemd --version | head -n 1 | awk '{print $2}')"
[[ "$version" -ge 245 ]] || { echo 'systemd journal namespaces require systemd 245+' >&2; exit 1; }
available="$(df -Pk /var | awk 'NR==2 {print $4}')"
[[ "$available" -ge 1048576 ]] || { echo 'At least 1 GiB free space required' >&2; exit 1; }
echo 'Pi preflight passed.'
