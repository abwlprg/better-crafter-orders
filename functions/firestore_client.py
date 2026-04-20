"""Firestore client helpers for idempotent processed-email tracking."""

from __future__ import annotations

from dataclasses import dataclass

from firebase_admin import firestore


@dataclass(slots=True)
class ProcessedEmailRecord:
    """Stored metadata for a processed Gmail message."""

    message_id: str
    customer_name: str
    order_date: str


class ProcessedEmailStore:
    """Encapsulates Firestore deduplication operations."""

    def __init__(self, collection_name: str) -> None:
        """Initialize the store with the provided Firestore collection."""
        self._client = firestore.client()
        self._collection = self._client.collection(collection_name)

    def is_processed(self, message_id: str) -> bool:
        """Check if a message was previously processed, using a transaction."""
        transaction = self._client.transaction()
        doc_ref = self._collection.document(message_id)

        @firestore.transactional
        def _check(txn: firestore.Transaction) -> bool:
            snapshot = doc_ref.get(transaction=txn)
            return snapshot.exists

        return _check(transaction)

    def mark_processed(self, record: ProcessedEmailRecord) -> None:
        """Mark a message as processed atomically using a transaction."""
        transaction = self._client.transaction()
        doc_ref = self._collection.document(record.message_id)

        @firestore.transactional
        def _mark(txn: firestore.Transaction) -> None:
            snapshot = doc_ref.get(transaction=txn)
            if snapshot.exists:
                return

            txn.set(
                doc_ref,
                {
                    "message_id": record.message_id,
                    "processed_at": firestore.SERVER_TIMESTAMP,
                    "customer_name": record.customer_name,
                    "order_date": record.order_date,
                },
            )

        _mark(transaction)
