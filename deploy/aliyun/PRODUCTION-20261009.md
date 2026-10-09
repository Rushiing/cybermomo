# CyberMOMO production cutover — 2026-10-09

- Public entry: https://cybermomo.daydreamer.world on Pre-RICH 120.27.147.161, `/opt/cybermomo-prod`, Compose project `cybermomo-prod`.
- Application PR #15 merged as `bc64af9308581e2ec8ee04e765bc682275fe52da`. Runtime images are the rehearsal-verified `cybermomo-backend:aliyun-20261009` and `cybermomo-frontend:aliyun-20261009`; later commits in the PR changed documentation only. PostgreSQL 18.6/vector 0.8.2.
- User-provided replacement model key installed before cutover. Model and provider unchanged; no credentials in Git.
- Old Railway backend/frontend/cron source triggers disconnected and all three deployments confirmed REMOVED. Cron schedule cleared. PostgreSQL and its volume retained for rollback; billing cancellation is not complete.
- Final dump exported after old writers stopped. Source unchanged across export; restored 24 tables match row counts and complete-row fingerprints. Fingerprint rows must be sorted by table name because UNION ALL can return branches in parallel order.
- Applied `20261009_email_claim`: 23 original business tables remain identical, only Alembic revision and new claim table differ. Original 89 accounts, password hashes, IDs and history preserved.
- DNS A record `cybermomo` -> 120.27.147.161, TTL 600. Caddy public certificate valid; frontend 200, unauthenticated auth 401. Other Caddy routes preserved.
- Public HTTPS API acceptance from Pre-RICH: registration, password login, Secure/HttpOnly cookie, repeated authenticated requests, logout 204, wrong password 401, self-Agent SSE done and stored user/assistant history passed with the new key. Two isolated un-onboarded test accounts remain (IDs 90, 91); only ID 91 has one acceptance conversation. No original account was modified for testing. First test incorrectly expected logout 200; corrected to the existing 204 contract.
- Production backup target is `cybermomo-prod-postgres-1/cybermomo`. OSS upload/download succeeded at 2026-10-09T07:58:21Z; downloaded dump fully restored into separate `cybermomo_prod_restore_20261009`, all 25 table fingerprints identical. Daily timer 04:35 Asia/Shanghai plus jitter; same-region off-host backup, not cross-region DR.
- New observation timer enabled every 30 minutes. Railway scheduler is disabled; never enable both.
- QuestionOS homepage 200; Caddy, newrich-real and newrich-synthetic active. Available memory about 1484 MiB, swap 0 during bounded smoke; not a peak-load capacity certification.

## Outstanding acceptance and exit

The local browser encountered an enterprise security interstitial and was handed to the user. Real-user old-account recovery/history on the formal domain and normal-network/mobile acceptance remain pending. The recovery flow already passed isolated SMTP/database/browser rehearsal; no additional email was sent during cutover. Google OAuth callback/connectivity is not verified; old Google-only accounts use the approved original-email recovery path.

Both applications require observation and user acceptance before final Railway resource/plan cleanup. Inventory the exact retained databases/volumes and obtain concrete cleanup approval; user deadline is before 2026-10-20. Do not represent retained Railway resources as billing cancellation.

After target writes begin, rollback requires target stop-write, fresh backup and data reconciliation; never simply reopen the stale Railway database. See CUTOVER.md.
