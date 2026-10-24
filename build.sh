#!/bin/sh
# Build the NVFD DSM package.  The compiled nvfd binary is committed under
# package/bin so the SPK can be built without a compiler on the NAS.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

VERSION=$(sed -n 's/^version="\(.*\)"/\1/p' INFO)
[ -n "$VERSION" ] || { echo "cannot read version from INFO" >&2; exit 1; }

NVFD_BIN=${NVFD_BIN:-$ROOT/package/bin/nvfd}
NVFD_CLOCKS=${NVFD_CLOCKS:-$ROOT/package/bin/nvfd-clocks}
test -x "$NVFD_BIN" || { echo "missing executable nvfd: $NVFD_BIN" >&2; exit 1; }
test -f "$NVFD_CLOCKS" || { echo "missing nvfd-clocks: $NVFD_CLOCKS" >&2; exit 1; }

python3 -m py_compile "$ROOT/package/bin/backend.py"
python3 -m py_compile "$NVFD_CLOCKS"

chmod 755 "$NVFD_BIN" "$NVFD_CLOCKS" \
          package/bin/backend.py package/ui/api.cgi \
          package/tools/*.sh tools/*.sh scripts/*.sh 2>/dev/null || true
chmod 755 scripts/preinst scripts/postinst scripts/preuninst \
          scripts/postuninst scripts/preupgrade scripts/postupgrade \
          scripts/start-stop-status
chmod 644 INFO LICENSE PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG \
          conf/privilege package/ui/index.html package/ui/config package/ui/Main.js \
          package/systemd/*.service package/etc/*.json
rm -rf package/bin/__pycache__

rm -f package.tgz
tar --sort=name --mtime='UTC 2020-01-01' --owner=0 --group=0 --numeric-owner -czf package.tgz -C package .

mkdir -p dist
SPK="dist/NVFD-$VERSION.spk"
rm -f "$SPK"
tar --sort=name --mtime='UTC 2020-01-01' --owner=0 --group=0 --numeric-owner -cf "$SPK" \
    INFO LICENSE PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG conf package.tgz scripts

echo "built: $ROOT/$SPK"
sha256sum "$SPK"
