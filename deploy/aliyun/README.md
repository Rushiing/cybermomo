# CyberMOMO Alibaba Cloud migration · 2026-10-09

Deadline: user states migration and Railway exit must finish **before 2026-10-20**. This is the user-provided cutoff, not a verified Railway invoice date.

## Current production status

Production cutover completed on 2026-10-09; public HTTPS API checks and production OSS full restore passed. See [production record](PRODUCTION-20261009.md) for exact evidence and remaining scheduled-backup observation and Railway exit. The remaining sections describe historical rehearsal evidence, not the current running topology. Railway database/volume remain retained and billing is not cancelled.

## Historical source inventory

- Railway project `7e623f90-337b-4cf2-a0f1-da260b1abe78`; source commit `6761426fd18e237647feaca9d5a7cae832dbe5e0`.
- backend, frontend, Postgres and `acceptable-mindfulness` cron (every 30 minutes, `python scripts/cron_observation_sweep.py`). Cron must have exactly one active scheduler after cutover.
- PostgreSQL **18.6**, pgvector **0.8.2**, Alembic `20260513_add_password_auth`; 24 public tables, database 22 MB.
- 89 users, 82 with password hashes, 7 Google-only; 89 profiles, 88 md_documents, 600 agent_chats, 5342 agent_chat_messages, 1147 summaries. Other tables and full fingerprints are in private inventory.
- Source stays online during rehearsal. Final cutover requires draining background pipelines, disabling cron/old writes, a fresh consistent dump and content verification. Never run repair/sweep on copied real users during rehearsal.
- Preserve JWT secret, identities, profiles, platform/soft block lists and all conversation links. Avatars are database data URLs or remote URLs; no application persistent file volume was observed.

## Target and isolation

Pre-RICH `120.27.147.161`: retain QuestionOS and NewRICH services. At initial inventory: 1895 MiB available memory, 34 GB disk free, swap use 0. Recheck under load.

Rehearsal directory `/opt/cybermomo-rehearsal`, independent Compose project and PostgreSQL volume. Host ports only 127.0.0.1:13010 (web), 127.0.0.1:13011 (API). DB has no published port. Original dump is restored into `cybermomo`; the running acceptance API uses a separate **empty synthetic** database `cybermomo_acceptance`. No cron during rehearsal. Backend uses 2 workers (40 maximum pooled connections total) within 768 MiB; frontend 512 MiB; Postgres 384 MiB. This budget needs live verification, not a capacity guarantee.

Public target approved in migration planning: `https://cybermomo.daydreamer.world`. Compose/Caddy files are preparations, not proof of publication. Production cookies require HTTPS, even during browser acceptance; do not weaken cookie protection to make an HTTP rehearsal appear successful.

## Google-only account recovery (user approved)

- Only existing non-deleted Google accounts without a password are eligible. Unverified optional emails on password registrations never authorize recovery.
- Verify access to the original normalized email; preserve user ID, google_sub, profile and all history. Duplicate eligible emails fail closed.
- Random 256-bit token; store SHA256 only; 15-minute expiration, single use, previous token invalidated on resend. Per-account 60-second cooldown and 5 emails / rolling 24 hours, persisted across workers/restarts. SMTP failure consumes the budget to avoid ambiguous resend abuse.
- Request response does not reveal whether the account exists. Token confirmation sets a unique username and password on the original account and issues its normal session cookie. Never create a new linked account or overwrite an existing password.
- Migration adds only `email_account_claims`; old migrations are unchanged. SMTP is TLS authenticated; secrets are private runtime configuration, never committed.
- New `/recover` page and links in primary/compatibility sign-in pages. No prompt, matching, social policy or model changes.

## Acceptance / pending

Verified on 2026-10-09:

- API: 116 tests passed; Web typecheck, lint and final production build passed (existing lint warnings retained).
- Linux frontend/backend images run on Pre-RICH. PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2), vector 0.8.2; the upstream pgvector image originally contained 18.4, so the build pins the official 18.6 packages.
- Initial restore: all 24 tables matched source row counts and full content fingerprints. After the 18.6 upgrade, all 24 counts remain unchanged. This is a rehearsal snapshot, not final synchronization.
- One authorized recovery email was accepted by SMTP for the isolated synthetic account. Initial attempts failed at MAIL FROM before recipient/body transmission because the copied sender included a display name; configuration now uses the bare sender address. No real user account was changed. SMTP acceptance is not recipient inbox confirmation.
- Real PostgreSQL, two API workers: concurrent confirmation produces one 200 and one 400; original synthetic ID/profile/history preserved, password login succeeds, invalid password rejected, cookie Secure/HttpOnly/SameSite=None retained.
- Browser through SSH loopback: password login, refresh persistence and historical conversation listing passed. Synthetic model call returned “连接正常。” over SSE; user and assistant messages persisted. This is not formal-domain HTTPS acceptance or broad model-quality acceptance.
- Database restart exposed stale pooled connections; pool_pre_ping now repairs them. Twenty authenticated requests after another DB restart all returned 200. Compose uses exec for Uvicorn signal propagation; restart the frontend after backend recreation to refresh proxy connections.
- Measured after the synthetic call: backend 215 MiB, frontend 26 MiB, DB 46 MiB; server available memory about 1587 MiB, swap use 0, disk free 32 GiB. This is a bounded smoke, not peak-concurrency capacity certification.

- Broader synthetic workflow: 1 match completed, 6 hooks, 6 Agent chat messages, 2 host summaries. Authenticated summary list and chat replay returned the correct host-scoped result.
- Dedicated RAM user `cybermomo-backup`, custom policy `CyberMOMOBackupPrefixAccess`: only ListObjects on cybermomo/ and PutObject/GetObject on cybermomo/*; no console login or delete permission. Runtime list test allowed cybermomo/ and denied questionos/. Credentials exist only in `/opt/cybermomo-backup/ossutil.conf` (0600); both temporary downloaded CSV copies were removed after exact server readback.
- First OSS backup succeeded at 2026-10-09T07:14:34Z. Upload uses AES256 and forbid-overwrite; downloaded archive matched byte-for-byte. Full restore into `cybermomo_oss_verify` matched all 24 table row counts and complete content fingerprints. This is same-region off-host backup.
- `cybermomo-backup.timer` enabled, every day 04:35 Asia/Shanghai plus up to 120 seconds jitter; next observed run 2026-10-10 04:36:10 CST. At that rehearsal checkpoint it backed up the rehearsal snapshot. Final cutover must repoint it to the production container and validate a production backup.
- Recovery migration was also applied to an independent restored DB; the 23 original data tables remained content-identical, with only the new claim table and expected Alembic revision change. Observation cron ran once against synthetic acceptance DB and scheduled zero jobs.
- Source snapshot has 7 Google-only users, all 7 have unique normalized emails and no preexisting usernames, so the approved recovery path covers this cohort.
- Existing QuestionOS public homepage 200, unauthenticated auth endpoint 401; Caddy, newrich-real and newrich-synthetic services remain active.

At the rehearsal checkpoint, formal-domain HTTPS/legacy recovery acceptance, old scheduler drain and final synchronization were pending; the current completed status is in the production record. See [CUTOVER.md](CUTOVER.md) for the concrete approval scope and rollback boundary. Public Google OAuth callback is not yet configured/verified; the approved email path avoids reliance on Google connectivity.

Rehearsal dump SHA256: `d2025bae9be7cc0deaa8b54eaa069dc279a9bee697d034b3f67fcd6657fa6ed1`, 1,937,091 bytes. Private source evidence: `~/.config/cybermomo/migration-20261009/`.

QuestionOS OSS credential is limited to `questionos/`; do not reuse it for CyberMOMO. User approved the dedicated `cybermomo/` ListObjects/PutObject/GetObject policy and non-console RAM identity. RAM user creation, private credential transfer, policy attachment, upload/download and full restore verification completed. Existing bucket is in Hangzhou: off-host backup, not cross-region DR.

## Cutover gate

Once rehearsal passes: present exact stop/drain/final-sync/DNS/HTTPS/cron/backup changes and rollback plan for cutover approval. Retain Railway DB/volume until both migrations are accepted and cleanup list is explicitly approved. No Railway cancellation or deletion during rehearsal.
