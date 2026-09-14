# Verification — TOSM Bot v7

Verified 2026-09-10. These results concern the delivered code, not a running production deployment.

## Passed

- 33 automated Python tests, run with `python -m unittest discover -s tests -v` on Python 3.12 and aiohttp 3.13.5.
- Syntax parsing for every Python file, including Discord entrypoint.
- Sonnet 5 HTTP request contract: exact model `claude-sonnet-5`, no unsupported sampling parameters, explicit thinking mode, text-block selection, incomplete output rejection.
- Evidence validation: missing/duplicate IDs, invented quotes, unknown knowledge IDs, unsafe extra model fields rejected or discarded.
- Second-pass analysis approval/rejection handling with mocked model outputs.
- Report case with 55 messages: every source included in analysis batches and ledger; unique users and message totals computed in code.
- Incomplete classification and failed analysis retain counts and explicitly mark incompleteness.
- Approved knowledge text displayed from supplied records; unverified game facts are not inserted into knowledge automatically.
- Unknown user IDs remain unknown rather than inferred from display names.
- Local HTTP server transport with Thai JSON round trip and redacted remote errors.
- UTF-8 CSV import, duplicate detection, header validation, read-only SQLite migration and removal of legacy AI summaries from imported inputs.
- Bangkok/UTC day boundary handling.
- Durable outbox retains messages after failed transfer and across a new Outbox instance; retry removes only successful transfers.
- Database report-save failure propagates instead of being reported as success.

## Actual PostgreSQL checks passed

Executed the shipped SQL plus synthetic data assertions inside isolated schema `tosm_verify_20260910` in a single transaction on Supabase PostgreSQL. All changes were rolled back. A separate query confirmed the test schema no longer existed.

Checked schema/function syntax, service-role access, authenticated-role denial, atomic claim batching, lease ownership, completion updates, failed-record reset, snapshot row totals, scheduled-job deduplication, duplicate source insert handling, approved/unapproved/expired/future knowledge filtering, and exclusive end-of-period boundaries.

No production TOSM tables or data were created, migrated, or changed. Test results do not establish live REST gateway credentials or configuration.

## Not run live

- Sonnet 5 inference with the user's Anthropic account: no API key supplied.
- Discord login, command registration and scheduled message delivery: no bot token supplied. Discord runtime dependencies could not be installed in the restricted execution environment; entrypoint syntax was checked, not a live Discord session.
- Production Supabase REST integration or permanent schema installation: target project not confirmed; no backend key supplied.
- Migration of actual historical feedback: original archive contained code only, not SQLite/CSV data.
- Factual report-quality evaluation against real TOSM rules and raw feedback: those sources were not supplied. Model mocks validate mechanics, not semantic accuracy.

## Before switching the live bot

Follow README_TH.md to select a project, apply schema.sql, fill .env, import original data and approved knowledge, run check_connection.py --ai, then test /database_status, /backfill and /report_now in Discord. Review one daily report against its evidence before relying on automatic delivery.
