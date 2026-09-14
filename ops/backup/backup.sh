#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-35}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
TELEGRAM_API_BASE="${TELEGRAM_API_BASE:-https://api.telegram.org}"

required_env() {
  local name
  for name in \
    POSTGRES_HOST \
    POSTGRES_DB \
    POSTGRES_USER \
    POSTGRES_PASSWORD \
    TELEGRAM_BOT_TOKEN \
    TELEGRAM_CHAT_ID \
    BACKUP_AGE_RECIPIENT; do
    if [[ -z "${!name:-}" ]]; then
      echo "Missing required environment variable: ${name}" >&2
      exit 2
    fi
  done
}

telegram_call() {
  local method="$1"
  shift
  local response
  response="$(mktemp)"
  if ! curl \
    --silent \
    --show-error \
    --fail-with-body \
    --retry 5 \
    --retry-delay 2 \
    --retry-all-errors \
    --connect-timeout 10 \
    --max-time 900 \
    --output "$response" \
    "$@" \
    "${TELEGRAM_API_BASE}/bot${TELEGRAM_BOT_TOKEN}/${method}"; then
    cat "$response" >&2 || true
    rm -f "$response"
    return 1
  fi
  if ! grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' "$response"; then
    cat "$response" >&2 || true
    rm -f "$response"
    return 1
  fi
  rm -f "$response"
}

telegram_message() {
  local text="$1"
  telegram_call sendMessage \
    --request POST \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${text}"
}

telegram_document() {
  local path="$1"
  local caption="$2"
  telegram_call sendDocument \
    --request POST \
    --form-string "chat_id=${TELEGRAM_CHAT_ID}" \
    --form-string "caption=${caption}" \
    --form "document=@${path}"
}

notify_failure() {
  local exit_code="$?"
  trap - ERR
  telegram_message "BukvoGon backup FAILED on $(date -u +'%Y-%m-%d %H:%M UTC'). Encrypted local generations were not deleted. Check backup container logs." >/dev/null 2>&1 || true
  exit "$exit_code"
}

required_env
trap notify_failure ERR

mkdir -p "$BACKUP_ROOT"
timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
generation="${BACKUP_ROOT}/${timestamp}"
workdir="$(mktemp -d "/tmp/bukvogon-backup-${timestamp}.XXXXXX")"
trap 'rm -rf "$workdir"' EXIT
mkdir -p "$generation"

dump_path="${workdir}/bukvogon-${timestamp}.dump"
encrypted_path="${workdir}/bukvogon-${timestamp}.dump.age"
manifest_path="${generation}/bukvogon-${timestamp}.manifest.txt"
checksums_path="${generation}/bukvogon-${timestamp}.parts.sha256"
parts_prefix="${generation}/bukvogon-${timestamp}.dump.age.part-"

export PGPASSWORD="$POSTGRES_PASSWORD"

echo "[backup] creating PostgreSQL dump ${timestamp}"
pg_dump \
  --host="$POSTGRES_HOST" \
  --port="$POSTGRES_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --format=custom \
  --compress=9 \
  --file="$dump_path"

pg_restore --list "$dump_path" >/dev/null

echo "[backup] encrypting dump for configured age recipient"
age -r "$BACKUP_AGE_RECIPIENT" -o "$encrypted_path" "$dump_path"
[[ -s "$encrypted_path" ]]
rm -f "$dump_path"

encrypted_sha256="$(sha256sum "$encrypted_path" | awk '{print $1}')"
encrypted_bytes="$(wc -c < "$encrypted_path" | tr -d ' ')"

split -b 45m -d -a 4 "$encrypted_path" "$parts_prefix"
mapfile -t parts < <(find "$generation" -maxdepth 1 -type f -name 'bukvogon-*.dump.age.part-*' | sort)
if [[ "${#parts[@]}" -eq 0 ]]; then
  echo "Backup splitting produced no parts" >&2
  exit 3
fi

: > "$checksums_path"
for part in "${parts[@]}"; do
  (
    cd "$generation"
    sha256sum "$(basename "$part")"
  ) >> "$checksums_path"
done

cat > "$manifest_path" <<EOF
BUKVOGON_BACKUP_V1
timestamp=${timestamp}
database=${POSTGRES_DB}
encrypted_filename=$(basename "$encrypted_path")
encrypted_sha256=${encrypted_sha256}
encrypted_bytes=${encrypted_bytes}
part_count=${#parts[@]}
checksums_file=$(basename "$checksums_path")
EOF

(
  cd "$generation"
  sha256sum -c "$(basename "$checksums_path")" >/dev/null
)

telegram_message "BukvoGon weekly backup ${timestamp}: full PostgreSQL dump validated, age-encrypted, ${#parts[@]} part(s), ${encrypted_bytes} encrypted bytes. Manifest and all parts follow."
telegram_document "$manifest_path" "BukvoGon backup manifest ${timestamp}"
telegram_document "$checksums_path" "BukvoGon part checksums ${timestamp}"

for index in "${!parts[@]}"; do
  human_index="$((index + 1))"
  telegram_document "${parts[$index]}" "BukvoGon backup ${timestamp} · part ${human_index}/${#parts[@]}"
done

trap - ERR

# Retention runs only after a complete, validated and delivered generation exists.
find "$BACKUP_ROOT" \
  -mindepth 1 \
  -maxdepth 1 \
  -type d \
  -mtime "+${BACKUP_RETENTION_DAYS}" \
  -print \
  -exec rm -rf {} +

echo "[backup] completed ${timestamp}; encrypted SHA-256 ${encrypted_sha256}"
