#!/bin/sh
# Approve the NVFD package user in DSM's SimplePermissionManager and repair the
# NVFD systemd service.  Run this only if the package UI reports
# "backend execution failed", or after a package reinstall / SPM update.
set -e
if [ "$(id -u)" != "0" ]; then
    echo "run as root: sudo $0" >&2
    exit 1
fi
PERM=/var/packages/SimplePermissionManager/etc/permissions.json
if [ ! -f "$PERM" ]; then
    echo "SimplePermissionManager not found: $PERM" >&2
    exit 1
fi
cp "$PERM" "$PERM.bak.nvfd"
python3 - <<'PY'
import json
import pwd

path = "/var/packages/SimplePermissionManager/etc/permissions.json"
with open(path) as f:
    data = json.load(f)

user = pwd.getpwnam("NVFDControl")
entry = {
    "name": "NVFDControl",
    "uid": user.pw_uid,
    "gid": user.pw_gid,
    "package": "NVFDControl",
    "enabled": True,
}
data.setdefault("users", {})["NVFDControl"] = {
    "name": "NVFDControl", "uid": user.pw_uid, "gid": user.pw_gid, "enabled": True
}
data.setdefault("packages", {})["NVFDControl"] = entry
with open(path, "w") as f:
    json.dump(data, f, indent=4)
PY
chmod 755 "$PERM"
echo "NVFDControl approved."

PKG=/var/packages/NVFDControl/target
if [ -f "$PKG/systemd/nvfd.service" ]; then
    mkdir -p /etc/nvfd
    [ -f /etc/nvfd/config.json ] || cp "$PKG/etc/default_config.json" /etc/nvfd/config.json
    [ -f /etc/nvfd/curve.json ] || cp "$PKG/etc/default_curve.json" /etc/nvfd/curve.json
    [ -f /etc/nvfd/clocks.json ] || cp "$PKG/etc/default_clocks.json" /etc/nvfd/clocks.json
    chmod 644 /etc/nvfd/config.json /etc/nvfd/curve.json /etc/nvfd/clocks.json
    install -m 644 "$PKG/systemd/nvfd.service" /etc/systemd/system/nvfd.service
    systemctl daemon-reload
    systemctl enable nvfd >/dev/null 2>&1
    systemctl restart nvfd
    echo "NVFDControl service installed and started."
fi
