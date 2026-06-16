#!/usr/bin/env bash

# Shared frontend build helpers for UCloud. Caller must set APP_DIR and call
# ensure_node20 before invoking these functions.

frontend_build_marker() {
  printf "%s/frontend/.next/viewtube-build-revision" "$APP_DIR"
}

frontend_current_revision() {
  git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || printf "unknown"
}

frontend_built_revision() {
  local marker
  marker="$(frontend_build_marker)"
  if [[ -f "$marker" ]]; then
    cat "$marker"
  fi
}

build_frontend() {
  local revision marker
  revision="$(frontend_current_revision)"
  marker="$(frontend_build_marker)"
  echo "Building Next.js app with Node $(node --version) for revision $revision"
  npm --prefix "$APP_DIR/frontend" run build
  mkdir -p "$(dirname "$marker")"
  printf "%s\n" "$revision" > "$marker"
}

frontend_build_needs_refresh() {
  local revision built
  revision="$(frontend_current_revision)"
  built="$(frontend_built_revision)"

  if [[ ! -d "$APP_DIR/frontend/.next" ]]; then
    echo "Next build output missing."
    return 0
  fi

  if [[ -z "$built" ]]; then
    echo "Next build revision marker missing."
    return 0
  fi

  if [[ "$built" != "$revision" ]]; then
    echo "Next build revision is stale: built=$built current=$revision."
    return 0
  fi

  return 1
}

ensure_frontend_build_current() {
  if ! frontend_build_needs_refresh; then
    echo "Next build is current for revision $(frontend_current_revision)."
    return 0
  fi

  if [[ "${VIEWTUBE_AUTO_BUILD_ON_START:-1}" != "1" ]]; then
    echo "ERROR: Next build is missing or stale. Run scripts/ucloud_setup.sh or enable VIEWTUBE_AUTO_BUILD_ON_START=1." >&2
    return 1
  fi

  build_frontend
}
