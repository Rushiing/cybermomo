# CyberMOMO production and Railway exit

Current status: production runs on Alibaba Cloud; Railway exit completed on 2026-10-12. October 9 evidence below records the cutover; the exit checkpoint supersedes its retained-resource state.

## Production cutover evidence — 2026-10-09

- Public entry: https://cybermomo.daydreamer.world on Pre-RICH 120.27.147.161, `/opt/cybermomo-prod`, Compose project `cybermomo-prod`.
- Application PR #15 merged as `bc64af9308581e2ec8ee04e765bc682275fe52da`. Runtime images are the rehearsal-verified `cybermomo-backend:aliyun-20261009` and `cybermomo-frontend:aliyun-20261009`; later commits in the PR changed documentation only. PostgreSQL 18.6/vector 0.8.2.
- User-provided replacement model key installed before cutover. Model and provider unchanged; no credentials in Git.
- Old Railway backend/frontend/cron source triggers disconnected and all three deployments confirmed REMOVED. Cron schedule cleared. PostgreSQL and its volume were retained at this checkpoint; both were subsequently included in the October 12 project deletion.
- Final dump exported after old writers stopped. Source unchanged across export; restored 24 tables match row counts and complete-row fingerprints. Fingerprint rows must be sorted by table name because UNION ALL can return branches in parallel order.
- Applied `20261009_email_claim`: 23 original business tables remain identical, only Alembic revision and new claim table differ. Original 89 accounts, password hashes, IDs and history preserved.
- DNS A record `cybermomo` -> 120.27.147.161, TTL 600. Caddy public certificate valid; frontend 200, unauthenticated auth 401. Other Caddy routes preserved.
- Public HTTPS API acceptance from Pre-RICH: registration, password login, Secure/HttpOnly cookie, repeated authenticated requests, logout 204, wrong password 401, self-Agent SSE done and stored user/assistant history passed with the new key. Two isolated un-onboarded test accounts remain (IDs 90, 91); only ID 91 has one acceptance conversation. No original account was modified for testing. First test incorrectly expected logout 200; corrected to the existing 204 contract.
- Production backup target is `cybermomo-prod-postgres-1/cybermomo`. OSS upload/download succeeded at 2026-10-09T07:58:21Z; downloaded dump fully restored into separate `cybermomo_prod_restore_20261009`, all 25 table fingerprints identical. Daily timer 04:35 Asia/Shanghai plus jitter; same-region off-host backup, not cross-region DR.
- New observation timer enabled every 30 minutes. Railway scheduler is disabled; never enable both.
- QuestionOS homepage 200; Caddy, newrich-real and newrich-synthetic active. Available memory about 1484 MiB, swap 0 during bounded smoke; not a peak-load capacity certification.

## Acceptance boundary

The user confirmed old-account login and historical records on the new site on 2026-10-09. This closes that user acceptance item; the earlier enterprise browser interstitial is no longer an outstanding user-access blocker. Do not infer mobile-network or Google OAuth acceptance from this feedback. Google OAuth callback/connectivity remains unverified; Google-only accounts have the approved original-email recovery path.

Both applications have user-confirmed old-account/history acceptance. The required observation and scheduled-backup checks passed on October 12; Railway exit is complete. This does not close the Google OAuth, mobile-network or peak-capacity acceptance items.

## Railway exit and backup checkpoint — 2026-10-12

- User approved the exact two-project cleanup and subscription cancellation after reviewing the inventory. CyberMomo and QuestionOS project deletions returned success; the inventory covered eight services, two PostgreSQL volumes and no buckets. Final workspace readback: `projectCount=0`, `projects=[]`.
- Subscription readback: `cancelAtPeriodEnd=true`, `cancelAt=2026-10-24T07:23:24Z` (15:23:24 Asia/Shanghai). The plan remains `ACTIVE` until this boundary; renewal is cancelled. Accrued usage may still produce a final bill; a usage estimate is not a settled invoice.
- October 10, 11 and 12 production backup timers succeeded for both applications, including OSS download/byte comparison. Latest successes: QuestionOS October 12 04:15:42, CyberMOMO 04:36:54 Asia/Shanghai. The full restore evidence is from October 9; daily readback is not a new full restore test.
- Post-deletion checks: both formal HTTPS homepages 200 with valid TLS; QuestionOS monitor `ready=true`; CyberMOMO anonymous `/api/auth/me` 401. Production containers had no restarts or OOM; Caddy and NewRICH real/synthetic remained active. About 1363 MiB memory available, 32 GiB disk free, swap unused; this is a bounded health check, not peak-load certification.
- Final source dumps, private configuration archives, OSS backups and restore evidence are retained. Private exit receipt: `~/.config/railway-exit-20261012/RESULT.md`, with before/after API records and billing screenshot. Do not commit their private contents.
- Backup timers remain QuestionOS 04:15 and CyberMOMO 04:35 Asia/Shanghai (+0–120 seconds jitter). Backup scripts currently depend on `/opt/questionos-rehearsal/bin/ossutil`; the rehearsal directory is not disposable until that dependency has been migrated and verified.

## Recovery after Railway exit

There is no retained Railway deployment or database to restart. Stop affected writers/schedulers, take a fresh target backup, reconcile post-cutover changes, and restore a consistent current archive into an independent recovery target before reopening one writer and one scheduler. Never restore the October 9 source dump over current production. See [CUTOVER.md](CUTOVER.md) for the historical cutover scope.
