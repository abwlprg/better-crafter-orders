# Dedupe and Idempotency Design

## 1. Executive Summary

Production OneDrive writes must stay disabled until the app has row-level
idempotency. The current system can fetch the same Gmail thread through
overlapping date windows, manual retries, scheduler retries, webhook retries, or
operator-triggered catch-up paths. If those paths append directly to the Word
document without a durable ledger, the same order row can be written more than
once.

Idempotency must be solved before enabling real writes because OneDrive is the
business-facing document, not a transactional queue. Once duplicate rows are
inserted, cleanup becomes manual and risky. The design below treats every parsed
order row as an append candidate with a deterministic idempotency key, records
row-level processing state in Firestore, and allows retries to be safe by
turning already-claimed rows into duplicates instead of new appends.

## 2. Current System Behavior

The backend has several Gmail read paths. `GET /api/orders-stream` streams
read-only preview progress while fetching Gmail threads and parsing rows.
`GET /api/orders` does a similar non-streaming fetch. `POST /api/batch-orders`
is an admin-protected dry-run preview that supports supplier IDs `stephen` and
`steven`, validates date input, parses rows, and returns per-supplier summaries.
It does not write to OneDrive, mark messages processed, or write Firestore state.

The Gmail client uses `threads.list` and `threads.get`, keeps the oldest message
body as the source order text, and merges PDF text from later messages in the
same thread. The parser returns a list of row dictionaries because one email can
contain several order rows. `api.parse_message_to_order_rows` cleans parser
values, validates rows independently, and adds source metadata such as
`message_id`, `thread_id`, `supplier_id`, `supplier_name`, `email_subject`,
`email_date`, and `item_index`.

Dangerous write/delete/scheduler/webhook endpoints are currently protected by
`X-Admin-API-Key`. Those endpoints still contain OneDrive write code, so they
must not be treated as production-ready. The existing `functions/main.py`
scheduled flow also has message-level processed-email tracking, but it is not
sufficient for row-level idempotency and includes a known unsafe failure mode:
it can mark messages processed after a OneDrive write failure.

The OneDrive sandbox harness exists to validate Microsoft Graph credentials and
test-file write behavior against cloned/test files only. Sandbox success proves
auth and docx mutation mechanics, not production write safety.

No production write path should be enabled until row-level idempotency,
OneDrive backup/ETag protection, and failure recovery rules are implemented and
tested.

## 3. Definitions

- **Gmail message ID**: Gmail's immutable ID for one message payload. The current
  Gmail client records the oldest message ID in a thread as `message_id`.
- **Gmail thread ID**: Gmail's ID for a conversation thread. One thread can
  contain the original order plus replies, labels, PDFs, or corrections.
- **Supplier ID**: The app-level supplier key, currently `stephen` or `steven`
  for the dry-run batch endpoint.
- **Parsed order row**: One normalized dictionary returned from parser output
  and accepted by row validation.
- **Source email metadata**: The source identifiers and context attached to a
  parsed row, including supplier, Gmail message/thread IDs, subject, email date,
  and item index.
- **Idempotency key**: A deterministic row-level key used to decide whether an
  append candidate has already been claimed or committed.
- **Processing attempt**: One run of a read, parse, dedupe, append, and finalize
  workflow.
- **Append candidate**: A valid parsed row that may be written if its
  idempotency key is not already claimed or committed.
- **Committed append**: A row that the system believes was written to OneDrive
  and recorded in the ledger as appended.
- **Duplicate candidate**: A valid parsed row whose idempotency key already
  exists in the ledger.

## 4. Proposed Idempotency Key Strategy

Use a deterministic row-level key:

```text
supplier_id + gmail_thread_id + gmail_message_id + normalized_order_fingerprint
```

Thread-only dedupe is insufficient because one thread can produce multiple
orders. If the app used only `thread_id`, the first row would suppress all
sibling rows in the same email.

Message-only dedupe is also insufficient because one message can contain
multiple item rows. If the app used only `message_id`, a two-item order would be
reduced to one append.

The `normalized_order_fingerprint` should be a stable hash of normalized row
fields. Candidate fields:

- `supplier_id`
- customer or order identifier if the supplier provides one
- item/SKU or item code
- quantity
- order date
- ship-to/name/address fields when available
- source Gmail message ID
- `item_index` within the message when no stronger row identifier exists

Normalization should trim whitespace, collapse internal whitespace, lowercase
case-insensitive text, normalize date formats, and convert missing values to a
stable empty representation. The fingerprint should not include volatile fields
such as run timestamps, parser debug strings, raw email body, raw PDF text, or
environment values.

The first implementation can use `item_index` as part of the fallback identity,
but the design should prefer supplier-provided order numbers or item-level
business identifiers once Adrian/Leo confirm which fields are reliable.

## 5. Data Store Recommendation

Use Firestore for processed order row and append ledger state.

Firestore fits the current stack, supports atomic create-if-absent semantics,
and can hold both operational state and debugging metadata. It also gives future
UI and diagnostic flows a durable place to report duplicates, failed attempts,
or abandoned in-progress rows.

The existing message-level `processed_emails` collection should not be the final
source of truth for append safety. It can be left in place until replaced, but
production row appends should rely on a row-level ledger.

## 6. Proposed Firestore Schema

### `processed_order_rows/{idempotency_key}`

Fields:

- `idempotency_key`
- `supplier_id`
- `supplier_name`
- `gmail_thread_id`
- `gmail_message_id`
- `source_subject`
- `source_date`
- `normalized_fingerprint`
- `parser_version`
- `status`
- `first_seen_at`
- `last_seen_at`
- `appended_at`
- `batch_id`
- `onedrive_file_id`
- `row_summary`
- `error`
- `attempt_count`
- `lease_owner`
- `lease_expires_at`

Suggested statuses:

- `claimed`
- `append_in_progress`
- `appended`
- `duplicate`
- `append_failed`
- `needs_repair`
- `ignored_invalid`

`row_summary` should include only safe business fields required for debugging:
customer/display name, item code, quantity, order date, and ship date. It should
not include raw email bodies, raw PDF text, tokens, headers, or secrets.

### `processing_batches/{batch_id}`

Fields:

- `batch_id`
- `started_at`
- `completed_at`
- `dry_run`
- `supplier_ids`
- `date_range`
- `emails_found`
- `orders_parsed`
- `would_append`
- `appended`
- `duplicates`
- `invalid_rows`
- `errors`
- `trigger`
- `app_version`

Indexes:

- `processed_order_rows`: `supplier_id + status`
- `processed_order_rows`: `gmail_thread_id`
- `processed_order_rows`: `gmail_message_id`
- `processed_order_rows`: `batch_id`
- `processing_batches`: `started_at`

The document ID for `processed_order_rows` should be the idempotency key so the
claim operation can use create-if-absent.

## 7. Transaction / Race Condition Strategy

Avoid check-then-write. Use a transaction or Firestore create operation that
atomically creates `processed_order_rows/{idempotency_key}` only if absent.

Recommended flow:

1. Compute idempotency key for every valid row.
2. For each key, attempt an atomic claim with status `claimed` or
   `append_in_progress`.
3. If creation fails because the document exists, treat the row as a duplicate.
4. Append only rows whose claims were created by the current attempt.
5. After OneDrive write succeeds, mark those rows `appended`.
6. If append fails before upload, mark claimed rows `append_failed` and include
   safe error metadata.

For concurrent runs, only one run can claim a given key. A duplicate run should
never append rows whose keys are already claimed, in progress, appended, or
awaiting repair.

Use leases for `append_in_progress` rows. If a process crashes after claiming
but before finalizing, a later repair job can inspect `lease_expires_at`,
OneDrive state, and batch metadata before deciding whether to retry, mark
failed, or require manual review.

## 8. Failure Mode Matrix

| Case | Expected behavior | Recovery |
| --- | --- | --- |
| Parse fails | Record batch-level parse error; no idempotency row for missing parser output unless a safe invalid-row record is useful. | Fix parser and rerun dry-run first. |
| Invalid row | Count as invalid; do not append; optionally record `ignored_invalid` with safe row summary. | Improve parser or manually review. |
| Duplicate row | Existing idempotency key is reported as duplicate; do not append. | No action unless user requests review. |
| OneDrive write fails before append | Claimed rows become `append_failed`; no rows marked appended. | Retry after cause is fixed; transaction logic must allow safe retry or repair. |
| OneDrive write succeeds but Firestore commit fails | Highest-risk split-brain. Rows may be in OneDrive without committed ledger state. | Mark batch `needs_repair` if possible; repair by comparing backup/current document and source rows before retry. |
| Firestore claim succeeds but OneDrive write fails | Rows are claimed but not appended. | Mark `append_failed`; allow explicit retry after verifying no append occurred. |
| Process crashes mid-run | Some claims may remain `append_in_progress`. | Lease expiry plus repair workflow decides retry vs manual review. |
| Two schedulers run at once | Atomic claim allows one winner per row; losers report duplicates. | No manual action unless lease rows get stuck. |
| Same thread appears in multiple date windows | Same row-level key appears; later window reports duplicate. | No action. |
| Supplier correction/re-send | New message/thread or changed fingerprint should not silently overwrite. | Treat as new candidate or manual-review correction depending on policy. |
| Parser version changes | Fingerprint may change if normalized fields change. | Store `parser_version`; dry-run duplicate report should show potential parser-version drift before writes. |
| Manual reprocess requested | Default behavior still dedupes; explicit admin reprocess must be reviewable and auditable. | Add future override mode that never silently appends over existing ledger. |

## 9. Dry-Run Behavior

Dry-run must compute idempotency keys but must not create, update, or delete
idempotency records. It may read the dedupe store once that store exists, so it
can report `would_append`, `duplicates`, `invalid_rows`, and `errors`.

Until the store exists, current dry-run responses can keep `duplicates: null`.
This is safer than pretending to know duplicate state. Dry-run must never mark
messages or rows processed.

## 10. OneDrive Sandbox Relationship

The OneDrive sandbox harness validates Microsoft Graph auth, metadata reads,
and cloned/test-file docx mutation behavior. It does not validate production
idempotency.

Sandbox success does not mean production writes are safe. Production writes also
require:

- row-level dedupe ledger
- atomic Firestore claims
- OneDrive backup or snapshot before write
- ETag or equivalent concurrency protection
- repair flow for split-brain failures
- tests for retries and concurrent runs

## 11. Production Write Algorithm

Pseudo-code only:

```text
start batch record
fetch messages
for each message:
  parse rows
  normalize rows
  attach source metadata
  validate rows
  compute idempotency key for each valid row

for each append candidate:
  atomically create processed_order_rows/{idempotency_key}
  if already exists:
    count duplicate
  else:
    add to claimed_rows

if claimed_rows is empty:
  finalize batch and return summary

create OneDrive backup/snapshot metadata
download OneDrive document with ETag
append claimed rows to local document copy
upload with ETag precondition

if upload succeeds:
  mark claimed rows appended
  finalize batch success
else:
  mark claimed rows append_failed or needs_repair
  finalize batch failure
  raise/report safe error
```

This algorithm must not be implemented in production code until the helper,
store abstraction, dry-run integration, OneDrive backup/ETag protection, and
tests exist.

## 12. Required Tests Before Production Write

- Same row processed twice appends once.
- Same thread with two rows appends two distinct rows.
- Same message with two rows appends two distinct rows.
- Partial invalid rows do not discard valid sibling rows.
- Concurrent duplicate attempts allow only one append.
- Crash after claim but before OneDrive write is recoverable.
- Crash after OneDrive upload but before Firestore finalize is flagged for
  repair.
- Dry-run computes keys but never writes ledger state.
- Supplier correction/re-send behavior matches the chosen policy.
- Parser-version changes are visible and do not silently duplicate rows.
- OneDrive sandbox write only touches test file IDs.
- Sandbox harness refuses production IDs.
- Production endpoints remain protected by admin auth.
- No raw email body, PDF text, tokens, or secrets appear in ledger records.

## 13. Migration / Backfill Considerations

Rows already appended before row-level dedupe may not have enough source
metadata in the Word document to reconstruct perfect idempotency keys. A full
backfill could be imperfect and should not delete or rewrite production data.

Safer initial approach:

1. Start row-level protection for future writes only.
2. Use dry-run to compare would-be rows against the future ledger.
3. Optionally build a manual backfill tool later that reads existing rows and
   creates low-confidence ledger records for review.
4. Never delete production rows as part of backfill.

If backfill is required, it should be its own prompt with read-only inspection
first and explicit approval before any ledger writes.

## 14. Open Decisions

- Which fields reliably identify an order for Stephen/Steven?
- Do supplier corrections replace old rows, append as new versions, or go to
  manual review?
- Should the final source-of-truth ledger be only Firestore, or should OneDrive
  row IDs be mirrored in the document?
- How should manual reprocess work?
- Should duplicates be hidden, reported, or reviewable in the UI?
- What parser version string should be used for regex and Gemini outputs?
- How long should in-progress leases live before repair is allowed?
- What OneDrive backup/ETag strategy should be mandatory before upload?

## 15. Implementation Plan

- Prompt #11: Implement idempotency key helper and unit tests.
- Prompt #12: Add Firestore processed-order-row store abstraction.
- Prompt #13: Integrate dedupe with dry-run preview.
- Prompt #14: Add OneDrive backup/ETag write safety.
- Prompt #15: Enable protected write path with idempotency.
