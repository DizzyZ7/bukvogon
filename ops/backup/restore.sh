#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

manifest_path="${1:-}"
if [[ -z "$manifest_path" || ! -f "$manifest_path" ]]; then
  echo "Usage: BACKUP_AGE_IDENTITY_FILE=/path/to/key RESTORE_CONFIRM=YES restore.sh /backups/<generation>/*.manifest.txt" >&2
  exit 2
fi

required_env() {
  local name
  for name in \
    BACKUP_AGE_IDENTITY_FILE \
    RESTORE_POSTGRES_HOST \
    RESTORE_POSTGRES_DB \
    RESTORE_POSTGRES_USER \
    RESTORE_POSTGRES_PASSWORD; do
    if [[ -z "${!name:-}" ]]; then
      echo "Missing required environment variable: ${name}" >&2
      exit 2
    fi
  done
}

required_env

if [[ "${RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "Refusing destructive restore. Set RESTORE_CONFIRM=YES only after verifying the target database." >&2
  exit 3
fi

if [[ ! -f "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  echo "Age identity file does not exist: ${BACKUP_AGE_IDENTITY_FILE}" >&2
  exit 2
fi

backup_dir="$(cd "$(dirname "$manifest_path")" && pwd)"
manifest_path="${backup_dir}/$(basename "$manifest_path")"

manifest_value() {
  local key="$1"
  awk -F= -v wanted="$key" '$1 == wanted {print substr($0, index($0, "=") + 1); exit}' "$manifest_path"
}

timestamp="$(manifest_value timestamp)"
encrypted_filename="$(manifest_value encrypted_filename)"
encrypted_sha256="$(manifest_value encrypted_sha256)"
checksums_file="$(manifest_value checksums_file)"
part_count="$(manifest_value part_count)"

if [[ -z "$timestamp" || -z "$encrypted_filename" || -z "$encrypted_sha256" || -z "$checksums_file" || -z "$part_count" ]]; then
  echo "Manifest is incomplete" >&2
  exit 4
fi

checksums_path="${backup_dir}/${checksums_file}"
if [[ ! -f "$checksums_path" ]]; then
  echo "Checksum file missing: ${checksums_path}" >&2
  exit 4
fi

(
  cd "$backup_dir"
  sha256sum -c "$checksums_file"
)

mapfile -t part_names < <(awk '{print $2}' "$checksums_path")
if [[ "${#part_names[@]}" -ne "$part_count" ]]; then
  echo "Part count mismatch: manifest=${part_count}, checksums=${#part_names[@]}" >&2
  exit 4
fi

for part_name in "${part_names[@]}"; do
  if [[ "$part_name" != "$(basename "$part_name")" || ! -f "${backup_dir}/${part_name}" ]]; then
    echo "Invalid or missing backup part: ${part_name}" >&2
    exit 4
  fi
done

workdir="$(mktemp -d "/tmp/bukvogon-restore-${timestamp}.XXXXXX")"
trap 'rm -rf "$workdir"' EXIT

encrypted_path="${workdir}/${encrypted_filename}"
dump_path="${workdir}/bukvogon-${timestamp}.dump"

for part_name in "${part_names[@]}"; do
  cat "${backup_dir}/${part_name}" >> "$encrypted_path"
done

echo "${encrypted_sha256}  ${encrypted_path}" | sha256sum -c -

age --decrypt -i "$BACKUP_AGE_IDENTITY_FILE" -o "$dump_path" "$encrypted_path"
pg_restore --list "$dump_path" >/dev/null

export PGPASSWORD="$RESTORE_POSTGRES_PASSWORD"
RESTORE_POSTGRES_PORT="${RESTORE_POSTGRES_PORT:-5432}"

pg_restore \
  --host="$RESTORE_POSTGRES_HOST" \
  --port="$RESTORE_POSTGRES_PORT" \
  --username="$RESTORE_POSTGRES_USER" \
  --dbname="$RESTORE_POSTGRES_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  "$dump_path"

echo "Restore completed for generation ${timestamp} into ${RESTORE_POSTGRES_DB}"
