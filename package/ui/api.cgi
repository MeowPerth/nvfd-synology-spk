#!/bin/sh
# CGI bridge between the DSM-hosted UI (running as the NVFD package user) and
# the root backend.  spm-exec is DSM's SimplePermissionManager helper; NVFD is
# approved in this NAS's permissions.json, so this runs the backend as root.

BASE="/var/packages/NVFD/target"
BACKEND="$BASE/bin/backend.py"
SPM_EXEC="/usr/local/bin/spm-exec"
QUERY_STRING="${QUERY_STRING:-}"
REQUEST_METHOD="${REQUEST_METHOD:-GET}"
ACTION=$(printf '%s' "$QUERY_STRING" | sed -n 's/.*action=\([^&]*\).*/\1/p')

json_error() {
    printf 'Content-Type: application/json; charset=utf-8\r\n'
    printf 'Cache-Control: no-store\r\n'
    printf 'X-Content-Type-Options: nosniff\r\n\r\n'
    printf '{"ok":false,"error":"%s"}\n' "$1"
    exit 0
}

# Status is read-only and may be fetched with GET.  Every mutation must be a
# POST carrying the custom header; this also blocks cross-site form CSRF.
case "$ACTION" in
    status|"")
        ;;
    *)
        [ "$REQUEST_METHOD" = "POST" ] || json_error "mutation requires POST"
        [ "${HTTP_X_NVFD:-}" = "1" ] || json_error "missing X-NVFD header"
        ;;
esac

if [ ! -x "$BACKEND" ]; then
    json_error "backend not installed"
fi
if [ ! -x "$SPM_EXEC" ]; then
    json_error "spm-exec not found"
fi

OUT=$("$SPM_EXEC" "$BACKEND" "$QUERY_STRING" 2>&1)

# The backend always emits JSON; if spm-exec itself failed, do not leak a shell
# error page to the browser.
case "$OUT" in
    \{*) ;;
    *) OUT='{"ok":false,"error":"backend execution failed"}' ;;
esac

printf 'Content-Type: application/json; charset=utf-8\r\n'
printf 'Cache-Control: no-store\r\n'
printf 'X-Content-Type-Options: nosniff\r\n\r\n'
printf '%s\n' "$OUT"
