# Multi-company Compliance Register

## Scope and invariants

The existing register is extended, not replaced. A company owns each state row and its licenses, COAs, bonds, annual reports, filing receipts, attachments, portal credentials, and audit events. There is one reusable register implementation and a unique company/jurisdiction pair; there are no company-specific tables or pages.

Existing records belong to **Allied Alliance Group Inc.**. Migrating them must preserve every original column value, row ID, PDF byte sequence, and document association. Live compliance data must never be reset to the bundled seed workbook. The seed is not a backup.

New entities get all 50 states plus the District of Columbia. Requirement copying uses an explicit allowlist. It must never copy numbers, statuses indicating possession, portal usernames/passwords, evidence, receipts, company-specific dates, completion history, or historical notes. General requirement notes and renewal structure are separate from company-specific notes/dates; required bond amount is separate from the actual held bond amount.

## Permission policy

- Super admins can access and manage every company and see the All Companies overview.
- Compliance admins may access permitted companies. Company-level permissions are enforced by the API, including direct PDF and portal-credential requests.
- Standard employees and managers retain no Compliance access.
- Archived companies retain their matrices, documents, and history; archive is not deletion. Their compliance data is read-only.
- State changes and document operations capture company identity when initiated; switching the selector cannot redirect an in-flight write to a different company.

## UI behavior

`/compliance` retains its existing cards, matrix, indicators, links, search, and type/status filters. The selector and matrix/editor headers identify the selected company. Manage Companies provides company details, add/edit/archive controls, and clickable summary filters. All Companies is a company summary table, not a mixed-state matrix.

Expiration filters are inclusive of today and the selected future day (30, 60, or 90). Expired items remain visible through Needs Review / Open Issues. Soon means within 90 days. Open Issues counts affected jurisdictions, so its total can be reconciled to the filtered matrix.

Company logos and PDFs are retrieved through authenticated endpoints. PDFs remain database-backed and replacements are additional records rather than overwrites. Secret values must never be included in audit payloads.

## Migration release gate

Do not apply an unreviewed migration to production. Before activation:

1. Stop compliance writes and capture the exact application revision and database schema.
2. Make a full database backup outside the ephemeral application filesystem, and verify restoreability. Include durable document bytes and the encryption-key records needed to decrypt existing credentials. Never print credentials in reports.
3. Snapshot original compliance columns, ordered row IDs, jurisdiction membership, status totals at a fixed date, and SHA256/length for every PDF.
4. Rehearse the migration on a restored copy using the production database family/version.
5. Run the idempotent migration and compare the snapshot. Any mismatch or orphan document blocks activation.
6. Confirm all 51 jurisdictions, existing numbers and dates, category totals, PDF opens, and credential retrieval for authorized users.
7. Run cross-company write/document/credential denial tests, blank/copy creation, filters, audit, permissions, and archive history tests.
8. Activate only after verification, retain the backup, and record the exact deployed source and migration hashes.

A green synthetic-fixture suite does **not** establish that the real production database was backed up or that every real production PDF opens. Those are separate deployment gates. No deployment or production data change is implicit in this codebase implementation.

### Offline migration command

From `backend/`, with the correct database already configured and **all writers stopped**, use `python -m app.models.compliance_migration --backup /durable-backups/allied-before-multicompany.dump` (use a new absolute Windows path for local SQLite). PostgreSQL requires compatible `pg_dump` and `pg_restore` binaries on PATH. Never put database passwords on the command line. The command refuses an existing backup destination, creates and checks the backup before DDL, then returns a verification manifest containing counts and hashes, not record contents. A successful repeat is a verified no-op.

Startup rejects legacy, incomplete, unverified, non-unique, or orphaned company/state/document structures. The migration leaves existing row IDs and encrypted data intact. Before deployment, restore the backup to a separate disposable database and independently reconcile it; a dump catalog check alone is not a restore test.

Existing compliance admins receive explicit Allied grants during migration (or one-time fresh initialization), preserving their access. There is no implicit admin fallback: removing a grant revokes access and normal reads cannot recreate it. Explicit `compliance_company_permissions` rows grant companies and can mark them read-only; creators receive access to their new company. Standard employees and managers remain denied. A future permission-management UI can use this centralized assignment structure without splitting the compliance register.

## Verification

Canonical commands from their respective directories:

- Backend: `.venv/Scripts/python.exe -m pytest tests -q` (Windows development environment).
- Frontend: `npm test` and `npm run build`.

Additional acceptance work should use disposable databases and a loopback-only test server. Browser tests may fixture authentication/onboarding while using the real Compliance router; label that boundary explicitly rather than claiming a real login was verified.

The pre-change baseline (`0e35f5f7e14574694fa586205e62d49c4f6599fd`) passed 109 backend tests and 23 frontend tests. Existing Python dependency deprecation warnings were present. Compare final results with the same runtime and dependencies.
