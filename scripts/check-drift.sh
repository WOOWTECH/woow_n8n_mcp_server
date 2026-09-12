#!/usr/bin/env bash
# Compare charts/n8n-mcp with what is running. Exit 0 = in sync, 1 = drift.
#   1. repo    vs release : helm template (this repo) <-> helm get manifest
#   2. cluster vs chart   : kubectl diff of the rendered chart against live objects
# Extra arguments go to `helm template`, e.g. -f my-extra-values.yaml.
#
#   CONTEXT=woow-k3s RELEASE=n8n-mcp NAMESPACE=woowtech-odoo \
#     VALUES=deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml scripts/check-drift.sh
#
# Step 2 is skipped before the takeover (no release yet): the objects are then
# still owned by kubectl and `helm get manifest` fails.
set -euo pipefail

CONTEXT="${CONTEXT:-woow-k3s}"
RELEASE="${RELEASE:-n8n-mcp}"
NAMESPACE="${NAMESPACE:-woowtech-odoo}"
VALUES="${VALUES:-deploy/woow-k3s/n8n-mcp-woowtech-odoo.yaml}"
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

helm template "$RELEASE" charts/n8n-mcp -n "$NAMESPACE" --skip-tests -f "$VALUES" "$@" > "$tmp/repo.yaml"

rc=0
if helm --kube-context "$CONTEXT" get manifest "$RELEASE" -n "$NAMESPACE" > "$tmp/release.yaml" 2>/dev/null; then
  # -B: helm get manifest ends with an extra blank line that helm template does not.
  if diff -u -B "$tmp/release.yaml" "$tmp/repo.yaml" > "$tmp/repo.diff"; then
    echo "1. repo == release ${RELEASE}"
  else
    echo "1. DRIFT: this repo renders differently from release ${RELEASE}:"
    cat "$tmp/repo.diff"
    rc=1
  fi
else
  echo "1. skipped: no Helm release ${RELEASE} in ${NAMESPACE} yet (not taken over)"
fi

set +e
kubectl --context "$CONTEXT" diff -f "$tmp/repo.yaml" > "$tmp/live.diff" 2>&1
krc=$?
set -e
case "$krc" in
  0) echo "2. cluster == chart (context ${CONTEXT})" ;;
  1) echo "2. DRIFT: live objects differ from the chart:"; cat "$tmp/live.diff"; rc=1 ;;
  *) cat "$tmp/live.diff" >&2; exit "$krc" ;;
esac
exit "$rc"
