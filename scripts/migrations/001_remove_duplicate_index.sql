-- Migration: 001_remove_duplicate_index.sql
-- Description: Drop duplicate unique index idx_insider_tx_uniq on insider_transactions.
-- Note: Table-level UNIQUE constraint insider_transactions_source_accession_record_hash_key already enforces uniqueness.

DROP INDEX IF EXISTS idx_insider_tx_uniq;
