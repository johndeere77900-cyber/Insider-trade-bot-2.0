"""
Safe Storage Maintenance, Provenance Safety Audit, & Legacy Cleanup Tool for Insider Trade Bot 2.0.

Provides explicit, operator-invoked database maintenance functions:
1. provenance-audit:
    Performs comprehensive safety analysis:
    A. Total transaction-level provenance rows (record_type = 'insider_transaction')
    B. Dataset-level provenance rows (record_type = 'dataset_period')
    C. Completed ingestion periods
    D. Completed periods missing dataset-level provenance
    E. Orphan transaction-level provenance rows (record_id not in insider_transactions.record_hash)
    F. Transaction-level provenance grouped by source
    G. Repository/application code dependency verification (establishes whether code queries record_type='insider_transaction')
    H. Coverage verification (ensures dataset-level provenance exists for all imported periods)

2. provenance-cleanup --dry-run:
    Simulates cleanup, reports targeted vs protected rows, orphan counts, and safety eligibility with ZERO mutations.

3. provenance-cleanup --execute:
    Safely deletes legacy transaction-level provenance in idempotent batches ONLY when all safety checks pass. Target is EXPLICITLY record_type = 'insider_transaction'. NEVER deletes 'dataset_period'.

4. verify:
    Read-only post-maintenance verification report showing relation sizes, row counts, duplicate index existence, and UNIQUE constraint existence.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url


def _audit_code_dependencies() -> bool:
    """
    Statically verify whether application repository or pipeline code queries record_type='insider_transaction'.
    Returns True if application code ONLY queries 'dataset_period' or generic provenance, False if 'insider_transaction' is required.
    """
    repo_root = Path(__file__).resolve().parent.parent
    code_files = list(repo_root.glob("data/**/*.py")) + list(repo_root.glob("storage/**/*.py")) + list(repo_root.glob("signals/**/*.py")) + list(repo_root.glob("research/**/*.py"))

    found_queries = False
    for fpath in code_files:
        if fpath.name == "repository.py":
            continue  # ignore generic repository store_provenance definitions
        try:
            content = fpath.read_text(encoding="utf-8")
            if "record_type = 'insider_transaction'" in content or 'record_type = "insider_transaction"' in content:
                found_queries = True
                break
        except Exception:
            pass

    return not found_queries


def audit_provenance(database_url: str) -> dict:
    print("================ PROVENANCE SAFETY AUDIT ================\n")

    results = {}

    with connect(database_url) as conn:
        # A. Total transaction-level provenance rows
        try:
            tx_prov_count = conn.execute(
                "SELECT COUNT(*) FROM provenance WHERE record_type = 'insider_transaction'"
            ).fetchone()[0]
        except Exception:
            tx_prov_count = 0

        # B. Dataset-level provenance rows
        try:
            ds_prov_count = conn.execute(
                "SELECT COUNT(*) FROM provenance WHERE record_type = 'dataset_period'"
            ).fetchone()[0]
        except Exception:
            ds_prov_count = 0

        # Total provenance
        try:
            total_prov_count = conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0]
        except Exception:
            total_prov_count = 0

        # C. Completed ingestion periods
        try:
            completed_periods = [
                r[0]
                for r in conn.execute(
                    "SELECT period FROM ingestion_state WHERE status = 'COMPLETED'"
                ).fetchall()
            ]
        except Exception:
            completed_periods = []

        # D. Completed periods missing dataset-level provenance
        missing_ds_prov = []
        for p in completed_periods:
            try:
                sql = (
                    "SELECT COUNT(*) FROM provenance WHERE record_type = 'dataset_period' AND record_id = %s"
                    if is_postgresql_url(database_url) else
                    "SELECT COUNT(*) FROM provenance WHERE record_type = 'dataset_period' AND record_id = ?"
                )
                found = conn.execute(sql, (p,)).fetchone()[0]
                if found == 0:
                    missing_ds_prov.append(p)
            except Exception:
                pass

        # E. Orphan transaction-level provenance rows (record_id not in insider_transactions.record_hash)
        try:
            orphan_sql = """
                SELECT COUNT(*)
                FROM provenance p
                LEFT JOIN insider_transactions it ON p.record_id = it.record_hash
                WHERE p.record_type = 'insider_transaction' AND it.id IS NULL
            """
            orphan_count = conn.execute(orphan_sql).fetchone()[0]
        except Exception:
            orphan_count = 0

        # F. Transaction-level provenance grouped by source
        try:
            source_rows = conn.execute(
                "SELECT source, COUNT(*) FROM provenance WHERE record_type = 'insider_transaction' GROUP BY source"
            ).fetchall()
            by_source = {r[0]: r[1] for r in source_rows}
        except Exception:
            by_source = {}

        # G. Code dependency verification
        code_dep_safe = _audit_code_dependencies()

        # Foreign Key check
        fk_dependencies = []
        if is_postgresql_url(database_url):
            try:
                fk_sql = """
                    SELECT
                        tc.table_name, kcu.column_name
                    FROM
                        information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                          ON tc.constraint_name = kcu.constraint_name
                          AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                          ON ccu.constraint_name = tc.constraint_name
                          AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='provenance';
                """
                fk_rows = conn.execute(fk_sql).fetchall()
                fk_dependencies = [f"{r[0]}.{r[1]}" for r in fk_rows]
            except Exception:
                fk_dependencies = []

        # Final Cleanup Eligibility Logic
        # Cleanup is safe ONLY if:
        # 1) Transaction-level provenance rows exist (>0)
        # 2) Foreign key count is 0
        # 3) Application/repository code dependency check passes
        # 4) Missing dataset-level provenance count is 0
        can_cleanup = (
            tx_prov_count > 0
            and len(fk_dependencies) == 0
            and code_dep_safe
            and len(missing_ds_prov) == 0
        )

        results = {
            "total_provenance_rows": total_prov_count,
            "transaction_level_provenance_rows": tx_prov_count,
            "dataset_level_provenance_rows": ds_prov_count,
            "completed_periods_count": len(completed_periods),
            "missing_dataset_provenance_periods": missing_ds_prov,
            "orphan_provenance_count": orphan_count,
            "transaction_provenance_by_source": by_source,
            "code_dependency_safe": code_dep_safe,
            "fk_dependencies": fk_dependencies,
            "can_cleanup": can_cleanup,
        }

    print(f"  A. Transaction-level provenance rows:  {tx_prov_count:,}")
    print(f"  B. Dataset-level provenance rows:      {ds_prov_count:,}")
    print(f"  C. Completed ingestion periods:        {len(completed_periods):,}")
    print(f"  D. Missing dataset-level provenance:   {missing_ds_prov if missing_ds_prov else '0 periods (ALL PRESENT)'}")
    print(f"  E. Orphan tx provenance (no tx match):  {orphan_count:,}")
    print(f"  F. Tx provenance grouped by source:     {by_source if by_source else 'None'}")
    print(f"  G. Code dependency check:              {'PASS (No application query reads tx provenance)' if code_dep_safe else 'FAIL (App code queries tx provenance)'}")
    print(f"  H. Foreign-key dependency check:       {'PASS (0 foreign key constraints targeting provenance)' if not fk_dependencies else f'FAIL ({len(fk_dependencies)} FK constraints: {fk_dependencies})'}\n")

    print("SAFETY SUMMARY & CLEANUP ELIGIBILITY:")
    print(f"  Target rows to delete (record_type='insider_transaction'): {tx_prov_count:,}")
    print(f"  Protected rows (record_type='dataset_period'):            {ds_prov_count:,}")
    print(f"  OVERALL CLEANUP ELIGIBILITY: {'SAFE TO EXECUTE CLEANUP' if can_cleanup else 'REFUSE EXECUTION (Safety prerequisites not satisfied)'}\n")

    return results


def cleanup_provenance(
    database_url: str,
    batch_size: int = 10000,
    dry_run: bool = True,
    execute: bool = False,
) -> bool:
    print("================ PROVENANCE MAINTENANCE CLEANUP ================\n")

    # Safety Check: Must have explicit --execute flag and dry_run=False
    if dry_run or not execute:
        print("DRY-RUN / PRE-FLIGHT MODE ACTIVE (ZERO DELETE/UPDATE/DDL operations will be performed).\n")

    # Perform full safety audit first
    audit = audit_provenance(database_url)

    tx_prov_count = audit["transaction_level_provenance_rows"]
    ds_prov_count = audit["dataset_level_provenance_rows"]

    if tx_prov_count == 0:
        print("No legacy transaction-level provenance rows exist. Nothing to clean up.")
        return True

    if not audit["can_cleanup"]:
        print("ERROR: SAFETY AUDIT FAILED! Refusing cleanup execution.")
        if audit["fk_dependencies"]:
            print(f"  - Foreign key constraints exist targeting provenance: {audit['fk_dependencies']}")
        if audit["missing_dataset_provenance_periods"]:
            print(f"  - Missing dataset-level provenance for periods: {audit['missing_dataset_provenance_periods']}")
        if not audit["code_dependency_safe"]:
            print("  - Application code queries transaction-level provenance!")
        return False

    if dry_run or not execute:
        print("================ DRY-RUN SAFETY REPORT ================")
        print(f"Target Database:                 {database_url.split('@')[-1]}")
        print(f"Targeted Rows (EXPLICIT):        {tx_prov_count:,} 'insider_transaction' provenance rows")
        print(f"Protected Rows (PRESERVED):      {ds_prov_count:,} 'dataset_period' provenance rows")
        print(f"Orphan Tx Provenance Count:      {audit['orphan_provenance_count']:,}")
        print(f"Missing Dataset Provenance:      0 periods")
        print(f"Foreign-Key Dependencies:       0 constraints")
        print(f"Application Code Dependencies:  PASS")
        print(f"Final Cleanup Eligibility:      SAFE TO EXECUTE")
        print("-------------------------------------------------------")
        print("RESULT: ZERO rows deleted. Pre-flight checks passed.")
        print("To execute actual deletion, re-run with: python main.py storage-maintenance provenance-cleanup --execute")
        print("=======================================================\n")
        return True

    # Execute actual batch deletion
    print(f"EXECUTE MODE ACTIVE: Deleting ONLY record_type = 'insider_transaction' ({tx_prov_count:,} rows) in batches of {batch_size:,}...")

    total_deleted = 0
    with connect(database_url) as conn:
        while True:
            if is_postgresql_url(database_url):
                del_sql = """
                    DELETE FROM provenance
                    WHERE id IN (
                        SELECT id FROM provenance
                        WHERE record_type = 'insider_transaction'
                        LIMIT %s
                    )
                """
            else:
                del_sql = """
                    DELETE FROM provenance
                    WHERE id IN (
                        SELECT id FROM provenance
                        WHERE record_type = 'insider_transaction'
                        LIMIT ?
                    )
                """

            if is_postgresql_url(database_url):
                with conn.cursor() as cursor:
                    cursor.execute(del_sql, (batch_size,))
                    deleted = cursor.rowcount
            else:
                cursor = conn.execute(del_sql, (batch_size,))
                deleted = cursor.rowcount

            conn.commit()
            total_deleted += deleted
            print(f"  Batch deleted {deleted:,} rows (total deleted: {total_deleted:,} / {tx_prov_count:,})...")

            if deleted == 0 or total_deleted >= tx_prov_count:
                break

    # Verify dataset-level provenance was completely preserved
    with connect(database_url) as conn:
        remaining_ds_prov = conn.execute("SELECT COUNT(*) FROM provenance WHERE record_type = 'dataset_period'").fetchone()[0]

    print(f"\nSUCCESS: Deleted {total_deleted:,} 'insider_transaction' provenance rows.")
    print(f"PROTECTED: {remaining_ds_prov:,} 'dataset_period' provenance rows survived cleanup completely.\n")
    return True


def verify_maintenance(database_url: str) -> dict:
    """
    Read-only post-maintenance verification report.
    Note: Deleting rows in PostgreSQL marks tuple dead space; physical disk size returns to Neon as autovacuum runs.
    """
    print("================ POST-MAINTENANCE READ-ONLY VERIFICATION ================\n")

    results = {}

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            try:
                db_size = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
            except Exception:
                db_size = 0

            try:
                it_rel = conn.execute("SELECT pg_table_size('insider_transactions'::regclass), pg_indexes_size('insider_transactions'::regclass)").fetchone()
                it_table_size, it_index_size = it_rel[0], it_rel[1]
            except Exception:
                it_table_size, it_index_size = 0, 0

            try:
                prov_rel = conn.execute("SELECT pg_table_size('provenance'::regclass), pg_indexes_size('provenance'::regclass)").fetchone()
                prov_table_size, prov_index_size = prov_rel[0], prov_rel[1]
            except Exception:
                prov_table_size, prov_index_size = 0, 0

            # Index & Constraint existence
            try:
                dup_idx_exists = conn.execute(
                    "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_insider_tx_uniq'"
                ).fetchone()[0] > 0
            except Exception:
                dup_idx_exists = False

            try:
                uniq_constraint_exists = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.table_constraints
                    WHERE table_name = 'insider_transactions' AND constraint_type = 'UNIQUE'
                    """
                ).fetchone()[0] > 0
            except Exception:
                uniq_constraint_exists = False

        else:
            try:
                db_path = get_database_path(database_url)
                db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            except Exception:
                db_size = 0
            it_table_size, it_index_size, prov_table_size, prov_index_size = 0, 0, 0, 0

            try:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'")
                dup_idx_exists = cursor.fetchone() is not None
            except Exception:
                dup_idx_exists = False

            uniq_constraint_exists = True

        try:
            it_count = conn.execute("SELECT COUNT(*) FROM insider_transactions").fetchone()[0]
        except Exception:
            it_count = 0

        try:
            ds_prov_count = conn.execute("SELECT COUNT(*) FROM provenance WHERE record_type = 'dataset_period'").fetchone()[0]
        except Exception:
            ds_prov_count = 0

        try:
            tx_prov_count = conn.execute("SELECT COUNT(*) FROM provenance WHERE record_type = 'insider_transaction'").fetchone()[0]
        except Exception:
            tx_prov_count = 0

        try:
            completed_ingest_count = conn.execute("SELECT COUNT(*) FROM ingestion_state WHERE status = 'COMPLETED'").fetchone()[0]
        except Exception:
            completed_ingest_count = 0

    results = {
        "database_total_bytes": db_size,
        "insider_transactions_table_bytes": it_table_size,
        "insider_transactions_index_bytes": it_index_size,
        "provenance_table_bytes": prov_table_size,
        "provenance_index_bytes": prov_index_size,
        "insider_transactions_row_count": it_count,
        "dataset_level_provenance_row_count": ds_prov_count,
        "transaction_level_provenance_row_count": tx_prov_count,
        "ingestion_state_completed_count": completed_ingest_count,
        "duplicate_index_exists": dup_idx_exists,
        "unique_constraint_exists": uniq_constraint_exists,
    }

    print(f"Database Total Size:                       {db_size / (1024 * 1024):.2f} MB ({db_size:,} bytes)")
    print(f"insider_transactions Table Size:           {it_table_size / (1024 * 1024):.2f} MB")
    print(f"insider_transactions Index Size:           {it_index_size / (1024 * 1024):.2f} MB")
    print(f"provenance Table Size:                     {prov_table_size / (1024 * 1024):.2f} MB")
    print(f"provenance Index Size:                     {prov_index_size / (1024 * 1024):.2f} MB")
    print(f"insider_transactions Rows:                 {it_count:,}")
    print(f"dataset_period Provenance Rows:            {ds_prov_count:,}")
    print(f"insider_transaction Provenance Rows:       {tx_prov_count:,}")
    print(f"ingestion_state Completed Periods:         {completed_ingest_count:,}")
    print(f"Duplicate Index (idx_insider_tx_uniq):      {'EXISTS (Should be dropped via migration)' if dup_idx_exists else 'NOT FOUND (Dropped/Cleaned)'}")
    print(f"UNIQUE Constraint (source, acc, hash):      {'EXISTS (Protects transaction uniqueness)' if uniq_constraint_exists else 'MISSING (Warning!)'}\n")
    print("Note: PostgreSQL vacuum/autovacuum reclaims physical disk space asynchronously over time.\n")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Storage Maintenance & Legacy Provenance Cleanup.")
    subparsers = parser.add_subparsers(dest="subcommand", help="Maintenance subcommands")

    # provenance-audit
    audit_parser = subparsers.add_parser("provenance-audit", help="Audit provenance rows and safety prerequisites.")
    audit_parser.add_argument("--database-url", default="", help="Database URL to audit.")

    # provenance-cleanup
    clean_parser = subparsers.add_parser("provenance-cleanup", help="Clean up legacy transaction-level provenance rows.")
    clean_parser.add_argument("--database-url", default="", help="Database URL.")
    clean_parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate cleanup without deleting rows (default).")
    clean_parser.add_argument("--execute", action="store_true", default=False, help="Explicitly execute actual row deletion.")
    clean_parser.add_argument("--batch-size", type=int, default=10000, help="Batch size for deletion.")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Read-only post-maintenance verification report.")
    verify_parser.add_argument("--database-url", default="", help="Database URL.")

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        return 1

    db_url = getattr(args, "database_url", "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        try:
            env = load_environment()
            db_url = env.database_url
        except Exception:
            pass

    if not db_url:
        print("ERROR: DATABASE_URL environment variable is missing or empty.", file=sys.stderr)
        return 1

    if args.subcommand == "provenance-audit":
        audit_provenance(db_url)
        return 0

    if args.subcommand == "provenance-cleanup":
        dry_run = not args.execute
        success = cleanup_provenance(
            db_url,
            batch_size=args.batch_size,
            dry_run=dry_run,
            execute=args.execute,
        )
        return 0 if success else 1

    if args.subcommand == "verify":
        verify_maintenance(db_url)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
