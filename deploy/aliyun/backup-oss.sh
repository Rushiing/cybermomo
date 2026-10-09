#!/usr/bin/env bash
# Isolated CyberMOMO backup, off-host readback, and archive validation.
set -euo pipefail
umask 077
base=/opt/cybermomo-backup
source "$base/backup.env"
: "${CM_BACKUP_CONTAINER:?}" "${CM_BACKUP_DATABASE:?}"
exec 9>"$base/backup.lock"
flock -n 9 || { echo 'Another backup is running' >&2; exit 1; }
trap 'date -u +%FT%TZ > "$base/last-failure"' ERR
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid)
destination="$base/archives/$stamp"
bash "$base/backup-container.sh" "$CM_BACKUP_CONTAINER" "$CM_BACKUP_DATABASE" "$destination"
oss=/opt/questionos-rehearsal/bin/ossutil
bucket=rushrich-backup-33407-20260713
key="cybermomo/$CM_BACKUP_DATABASE/$stamp"
for name in database.dump SHA256SUMS database-toc.txt; do
  "$oss" --config-file "$base/ossutil.conf" api put-object \
    --bucket "$bucket" --key "$key/$name" --body "file://$destination/$name" \
    --server-side-encryption AES256 --forbid-overwrite true > "$destination/upload-$name.json"
done
mkdir -m 700 "$destination/readback"
"$oss" --config-file "$base/ossutil.conf" cp \
  "oss://$bucket/$key/database.dump" "$destination/readback/database.dump"
cmp "$destination/database.dump" "$destination/readback/database.dump"
docker exec -i "$CM_BACKUP_CONTAINER" pg_restore --list \
  < "$destination/readback/database.dump" > "$destination/readback/database-toc.txt"
printf '%s\n' "$key" > "$destination/verified-oss-key"
printf '%s\n' "$(date -u +%FT%TZ) $key" > "$base/last-success"
echo "CyberMOMO backup and OSS readback verified: $stamp"
