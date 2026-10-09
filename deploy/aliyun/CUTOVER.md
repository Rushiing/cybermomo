# CyberMOMO production cutover checklist

Executed 2026-10-09 after user authorization. Server-side public HTTPS and production backup restore passed. See [production record](PRODUCTION-20261009.md) for evidence and remaining real-user/browser acceptance. The checklist below records the executed scope and rollback requirements.

## Authorized production scope

- Before merging this PR, inspect and suspend automatic deploy triggers for the old Railway backend/frontend/cron. Record the previous settings. A merge must not automatically restart the old writer or interrupt a live background pipeline; if deploy triggers cannot be safely suspended, keep the PR draft until the exit sequence is agreed.
- Railway CyberMOMO only: disable the `acceptable-mindfulness` 30-minute cron; stop old frontend/API writes after active background work drains. Keep Postgres, volume, deployment metadata and configuration for rollback.
- Export a new PostgreSQL custom dump after the stop-write boundary. Fingerprint every public table with count and canonical full-row content; recheck source is static. The rehearsal dump is not a final migration source.
- Deploy `/opt/cybermomo-prod` with independent Compose project/database volume. Stop only rehearsal frontend/API to release loopback ports 13010/13011; retain isolated databases/evidence. Never overwrite the production DB or a retained volume.
- Restore to the new empty production DB with pg_restore --exit-on-error; verify source fingerprints before applying only the new email-claim migration. Verify original 24 tables unchanged except the expected Alembic version; users retain IDs, password hashes and all history links.
- Configure WEB_BASE_URL/CORS for `https://cybermomo.daydreamer.world`, production authentication, original JWT/Google/model/admin settings, with the user-provided replacement model key and the validated SMTP bare sender address. Secrets stay private.
- Add only the approved `cybermomo.daydreamer.world` application DNS record to Pre-RICH and the Caddy fragment. Validate Caddy config before reload; obtain a valid public certificate. Preserve all existing QuestionOS/NewRICH/MCP/personal preview routes.
- Enable exactly one new observation scheduler only after old Railway cron is confirmed disabled and no old job remains. Install the prepared service/timer but do not enable it early.
- Repoint `/opt/cybermomo-backup/backup.env` to `cybermomo-prod-postgres-1` / `cybermomo`; run production OSS backup plus download/full restore validation. Existing timer 04:35 Asia/Shanghai (+0–120 seconds jitter) currently backs up the rehearsal snapshot, not live Railway data.

## Acceptance before declaring switched

- Public HTTPS, frontend assets, same-origin authenticated APIs and Origin-bearing POSTs; mock auth disabled and invalid auth rejected.
- Existing password login, refresh persistence, and user-approved old Google account recovery/history. The rehearsal email was synthetic and consumed; it is not real-account public-domain acceptance.
- Synthetic core paths: social matching, hooks, Agent chat, two host summaries; self-Agent SSE/history; no copied real-user model traffic during rehearsal.
- User acceptance from their normal network; browser security interstitials require user handling.
- Google OAuth from the new domain is not yet verified; approved original-email recovery is the domestic alternative. Do not present Google sign-in as working until redirect registration and server exchange are verified.
- Confirm observation scheduler uniqueness, backup last-success and restore evidence, host resources, QuestionOS and NewRICH availability.

## Rollback

Before target receives writes: stop target API/cron, restore previous Caddy/DNS routing as appropriate, restart retained Railway API/frontend/cron; verify old data fingerprint and live paths.

After target receives writes: do not just reopen the old DB. Stop new writes/cron, back up and reconcile target changes, restore a consistent current copy to the selected source, then reopen one writer and one scheduler. Returning DNS without data reconciliation would lose new activity.

No Railway database/volume deletion or billing cancellation is part of this cutover. After both applications pass observation and user acceptance, inventory exact retained services/resources and billing plan, obtain cleanup approval for the concrete list, then verify removal before the user-provided 2026-10-20 deadline.
