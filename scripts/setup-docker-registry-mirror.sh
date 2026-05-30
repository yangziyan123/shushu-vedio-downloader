#!/usr/bin/env sh
set -eu

MIRRORS="${DOCKER_REGISTRY_MIRRORS:-}"
TARGET="/etc/docker/daemon.json"

if [ -z "$MIRRORS" ]; then
    cat >&2 <<'EOF'
Set DOCKER_REGISTRY_MIRRORS first, for example:

DOCKER_REGISTRY_MIRRORS="https://your-docker-hub-mirror.example.com" sh scripts/setup-docker-registry-mirror.sh

If /etc/docker/daemon.json already exists, merge registry-mirrors manually or rerun with:

OVERWRITE_DOCKER_DAEMON_JSON=1 DOCKER_REGISTRY_MIRRORS="https://your-docker-hub-mirror.example.com" sh scripts/setup-docker-registry-mirror.sh
EOF
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    exec sudo DOCKER_REGISTRY_MIRRORS="$MIRRORS" OVERWRITE_DOCKER_DAEMON_JSON="${OVERWRITE_DOCKER_DAEMON_JSON:-0}" sh "$0"
fi

mkdir -p /etc/docker

if [ -f "$TARGET" ] && [ "${OVERWRITE_DOCKER_DAEMON_JSON:-0}" != "1" ]; then
    cat >&2 <<EOF
$TARGET already exists.
Merge this setting manually, or rerun with OVERWRITE_DOCKER_DAEMON_JSON=1 to replace it:

  "registry-mirrors": [
$(for mirror in $MIRRORS; do printf '    "%s",\n' "$mirror"; done | sed '$ s/,$//')
  ]
EOF
    exit 1
fi

if [ -f "$TARGET" ]; then
    cp "$TARGET" "$TARGET.bak.$(date +%Y%m%d%H%M%S)"
fi

tmp_file="$(mktemp)"
{
    printf '{\n'
    printf '  "registry-mirrors": [\n'
    first=1
    for mirror in $MIRRORS; do
        if [ "$first" -eq 1 ]; then
            first=0
        else
            printf ',\n'
        fi
        printf '    "%s"' "$mirror"
    done
    printf '\n'
    printf '  ]\n'
    printf '}\n'
} > "$tmp_file"

mv "$tmp_file" "$TARGET"

systemctl daemon-reload || true
systemctl restart docker
docker info | sed -n '/Registry Mirrors/,+8p'
