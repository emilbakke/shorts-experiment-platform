#!/usr/bin/env bash

# Shared Node.js bootstrap for UCloud jobs/VMs.
#
# UCloud VM images may not include Node.js, and the ViewTube frontend requires
# Node.js >=20.9. This helper first uses an existing suitable node, then a
# previously downloaded persistent Node install under /work/viewtube, then npx
# if available, and finally downloads an official Node.js binary tarball into
# the persistent folder without sudo.

node20_is_usable() {
  command -v node >/dev/null 2>&1 && node -e 'const [maj,min]=process.versions.node.split(".").map(Number); process.exit(maj>20 || (maj===20 && min>=9) ? 0 : 1)' >/dev/null 2>&1
}

node20_arch() {
  case "$(uname -m)" in
    x86_64 | amd64) printf "x64" ;;
    aarch64 | arm64) printf "arm64" ;;
    *)
      echo "ERROR: Unsupported CPU architecture for automatic Node.js install: $(uname -m)" >&2
      return 1
      ;;
  esac
}

install_persistent_node20() {
  local version="${VIEWTUBE_NODE_VERSION:-v20.11.1}"
  local arch
  arch="$(node20_arch)"
  local install_parent="${VIEWTUBE_NODE_PARENT:-$PERSIST_ROOT}"
  local install_dir="${VIEWTUBE_NODE_DIR:-$install_parent/node-$version-linux-$arch}"
  local archive="node-$version-linux-$arch.tar.xz"
  local url="https://nodejs.org/dist/$version/$archive"
  local tmp_dir="$install_parent/.node-download"

  if [[ -x "$install_dir/bin/node" ]]; then
    export PATH="$install_dir/bin:$PATH"
    return 0
  fi

  mkdir -p "$install_parent" "$tmp_dir"
  echo "Node.js >=20.9 not found; installing $version into $install_parent without sudo."
  echo "Downloading $url"

  if command -v curl >/dev/null 2>&1; then
    curl -fL "$url" -o "$tmp_dir/$archive"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$tmp_dir/$archive" "$url"
  else
    echo "ERROR: Need curl or wget to download Node.js $version." >&2
    return 1
  fi

  rm -rf "$tmp_dir/extract" "$install_dir.tmp"
  mkdir -p "$tmp_dir/extract"
  tar -xJf "$tmp_dir/$archive" -C "$tmp_dir/extract"
  mv "$tmp_dir/extract/node-$version-linux-$arch" "$install_dir.tmp"
  mv "$install_dir.tmp" "$install_dir"
  rm -rf "$tmp_dir"

  export PATH="$install_dir/bin:$PATH"
  node --version
  npm --version
}

ensure_node20() {
  if node20_is_usable; then
    return 0
  fi

  local version="${VIEWTUBE_NODE_VERSION:-v20.11.1}"
  local arch
  arch="$(node20_arch)"
  local install_parent="${VIEWTUBE_NODE_PARENT:-$PERSIST_ROOT}"
  local install_dir="${VIEWTUBE_NODE_DIR:-$install_parent/node-$version-linux-$arch}"

  if [[ -x "$install_dir/bin/node" ]]; then
    export PATH="$install_dir/bin:$PATH"
    if node20_is_usable; then
      return 0
    fi
  fi

  if [[ "${VIEWTUBE_NODE20_REEXEC:-0}" != "1" ]] && command -v npx >/dev/null 2>&1; then
    echo "Node.js >=20.9 not found; re-running via npx node@20."
    export VIEWTUBE_NODE20_REEXEC=1
    exec npx -y -p node@20 -c "bash '$0'"
  fi

  install_persistent_node20
  node20_is_usable || {
    echo "ERROR: ViewTube requires Node.js >=20.9, and automatic Node.js setup failed." >&2
    exit 1
  }
}
