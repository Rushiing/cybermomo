#!/usr/bin/env bash
# Local Docker PostgreSQL export. No passwords on the command line.
set -euo pipefail
umask 077
[[ $# == 3 ]] || { echo 'Usage: backup-container.sh CONTAINER DATABASE NEW_DIRECTORY' >&2; exit 2; }
container=$1
database=$2
destination=$3
case "$container" in
  cybermomo-rehearsal-postgres-1|cybermomo-prod-postgres-1) ;;
  *) echo 'Unexpected CyberMOMO container' >&2; exit 2 ;;
esac
case "$database" in
  cybermomo|cybermomo_acceptance) ;;
  *) echo 'Unexpected CyberMOMO database' >&2; exit 2 ;;
esac
[[ ! -e "$destination" ]] || { echo 'Refusing to overwrite existing backup' >&2; exit 2; }
docker exec "$container" pg_dump --version | grep -Eq ' 18\.'
[[ $(docker exec "$container" psql -U cybermomo -d "$database" -XAtc "SELECT to_regclass('public.users') IS NOT NULL AND to_regclass('public.agent_chats') IS NOT NULL AND to_regclass('public.agent_chat_messages') IS NOT NULL") == t ]] || {
  echo 'CyberMOMO tables not found' >&2; exit 2;
}
mkdir -m 700 "$destination"
docker exec "$container" pg_dump -U cybermomo -d "$database" --format=custom --no-owner --no-acl > "$destination/database.dump.partial"
docker exec -i "$container" pg_restore --list < "$destination/database.dump.partial" > "$destination/database-toc.txt"
mv "$destination/database.dump.partial" "$destination/database.dump"
(cd "$destination" && sha256sum database.dump > SHA256SUMS)
echo 'Backup archive verified; restore verification is a separate step.'
