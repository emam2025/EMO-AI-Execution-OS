# Phase I2 — ACID & Sync State Machine

## State Overview

The ACID Sync State Machine defines a **6-state lifecycle** for every
transaction that flows through the PostgreSQL Manager and Distributed Log
layers. Each transition is gated by **ACID Guards** that enforce Canon
LAW 14 (DAG Integrity), LAW 20 (Failure Detection), LAW 21 (Failure
Propagation), RULE 3 (Safety Guards), and RULE 4 (Isolation).

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `TX_START` | Transaction initiated, begin() issued | LAW 14 |
| `VALIDATION` | Pre-commit validation (isolation, partition key) | RULE 3 |
| `PARTITION_ROUTING` | Rows routed to correct partitions | LAW 11, RULE 4 |
| `COMMIT` | Commit issued, waiting for acks | LAW 20 |
| `ACK_REPLICA` | Replica acknowledged, transaction durable | LAW 21, RULE 4 |
| `ROLLBACK` | Transaction aborted, all changes reversed | RULE 5 |
| `DEADLOCK` | Deadlock detected, automatic retry pending | LAW 20 |

---

## Transition Map

```
   ┌──────────┐  A1   ┌────────────┐  A2   ┌──────────────────┐
   │ TX_START │──────>│ VALIDATION │──────>│ PARTITION_ROUTING│
   └──────────┘       └────────────┘       └──────────────────┘
                              │                      │
                              │A7 (guard fail)       │A3
                              v                      v
                         ┌──────────┐          ┌──────────┐
                         │ ROLLBACK │<─────────│  COMMIT  │
                         └──────────┘   A5     └──────────┘
                              ^                  │
                              │                  │A4
                              │                  v
                              │           ┌──────────────┐
                              │ A8        │ ACK_REPLICA  │
                              │           └──────────────┘
                              │
                         ┌──────────┐
                         │ DEADLOCK │
                         └──────────┘
                              │
                              │A6
                              v
                         ┌──────────┐
                         │ TX_START │ (retry with backoff)
                         └──────────┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| A1 | TX_START | VALIDATION | `guard_tx_initiated` | connection_acquired AND pool_has_room AND data_trace_id_provided | LAW 14, RULE 3 |
| A2 | VALIDATION | PARTITION_ROUTING | `guard_isolation_level` | isolation_level IS NOT NULL AND meets tx_requirement AND partition_key_verified = true | RULE 3 |
| A3 | PARTITION_ROUTING | COMMIT | `guard_partition_key` | partition_key_valid AND partition_exists AND rows_routed_correctly | LAW 11, RULE 4 |
| A4 | COMMIT | ACK_REPLICA | `guard_quorum_ack` | quorum_ack = majority AND replication_mode_met AND no_timeout | LAW 21, RULE 4 |
| A5 | COMMIT | ROLLBACK | `guard_commit_failed` | any_query_failed OR constraint_violation OR timeout_exceeded | RULE 5 |
| A6 | DEADLOCK | TX_START | `guard_deadlock_retry` | retry_count < max_retries AND backoff_waited | LAW 20, RULE 5 |
| A7 | VALIDATION | ROLLBACK | `guard_validation_failed` | isolation_level_invalid OR partition_key_missing OR data_trace_id_missing | RULE 3 |
| A8 | ACK_REPLICA | ROLLBACK | `guard_replica_failed` | replica_nack OR replica_timeout AND fallback_to_rollback | LAW 21, RULE 5 |

---

## ACID Guards (G1–G8)

### G1 — Transaction Initiation Guard (`guard_tx_initiated`)
**Prevents:** Starting a transaction without connection pool capacity or trace ID.

| Condition | Pass | Fail |
|-----------|------|------|
| connection_acquired_from_pool | ✅ | ❌ Block — pool exhausted |
| pool_has_room_for_retry | ✅ | ❌ Block — queue and wait |
| data_trace_id_provided | ✅ | ❌ Block — missing data_trace_id (LAW 5) |
| **LAW:** LAW 14, RULE 3 | | |

### G2 — Isolation Level Guard (`guard_isolation_level`)
**Prevents:** Executing a transaction without explicit isolation level.

| Condition | Pass | Fail |
|-----------|------|------|
| isolation_level IS NOT NULL | ✅ | ❌ Block — isolation not set |
| isolation_level meets tx_requirement | ✅ | ❌ Block — insufficient level |
| partition_key_verified = true | ✅ | ❌ Block — partition key unverified |
| **LAW:** RULE 3 (Safety Guards) | | |

### G3 — Partition Key Guard (`guard_partition_key`)
**Prevents:** Routing rows to non-existent or incorrect partitions.

| Condition | Pass | Fail |
|-----------|------|------|
| partition_key_valid AND NOT NULL | ✅ | ❌ Block — invalid key |
| partition_exists_for_key_range | ✅ | ❌ Block — no matching partition |
| rows_routed_correctly | ✅ | ❌ Block — routing mismatch |
| **LAW:** LAW 11 (No Global State), RULE 4 (Isolation) | | |

### G4 — Quorum Acknowledgement Guard (`guard_quorum_ack`)
**Prevents:** Committing without majority replica acknowledgement.

| Condition | Pass | Fail |
|-----------|------|------|
| quorum_ack_count >= majority | ✅ | ❌ Block — insufficient acks |
| replication_mode_met | ✅ | ❌ Block — mode not satisfied |
| ack_timeout_not_exceeded | ✅ | ❌ Block — ack timeout |
| **LAW:** LAW 21 (Failure Propagation), RULE 4 (Isolation) | | |

### G5 — Commit Failed Guard (`guard_commit_failed`)
**Prevents:** Allowing partial commit when queries fail.

| Condition | Pass | Fail |
|-----------|------|------|
| any_query_returned_error | ❌ (no errors) | ✅ Trigger rollback |
| constraint_violation_detected | ❌ (no violations) | ✅ Trigger rollback |
| timeout_exceeded | ❌ (within budget) | ✅ Trigger rollback |
| **LAW:** RULE 5 (Recovery) | | |

### G6 — Deadlock Retry Guard (`guard_deadlock_retry`)
**Prevents:** Infinite retry loops on deadlock.

| Condition | Pass | Fail |
|-----------|------|------|
| retry_count < max_retries | ✅ | ❌ Block — max retries exceeded |
| backoff_delay_waited | ✅ | ❌ Block — retry too soon |
| deadlock_detected_by_pg | ✅ | ❌ Not a deadlock situation |
| **LAW:** LAW 20 (Failure Detection), RULE 5 (Recovery) | | |

### G7 — Validation Failed Guard (`guard_validation_failed`)
**Prevents:** Proceeding with invalid transaction parameters.

| Condition | Pass | Fail |
|-----------|------|------|
| isolation_level_invalid | ❌ (valid) | ✅ Trigger rollback |
| partition_key_missing | ❌ (present) | ✅ Trigger rollback |
| data_trace_id_missing | ❌ (present) | ✅ Trigger rollback |
| **LAW:** RULE 3 (Safety Guards) | | |

### G8 — Replica Failed Guard (`guard_replica_failed`)
**Prevents:** Committing when replica acknowledgement fails without fallback.

| Condition | Pass | Fail |
|-----------|------|------|
| replica_returned_nack | ❌ (no nack) | ✅ Trigger rollback |
| replica_timeout_exceeded AND fallback_to_rollback | ✅ | ✅ Trigger rollback |
| leader_can_force_commit_without_replica | ❌ (must wait) | ✅ Block — no force |
| **LAW:** LAW 21 (Failure Propagation), RULE 5 (Recovery) | | |

---

## Deterministic Migration Guard

The Migration Guard guarantees that **the same sqlite_snapshot +
schema_mapping produces the same PostgreSQL state every time**,
preventing Non-Deterministic Data Drift.

### Formula

```
snapshot_hash = H(table_names || row_order || column_types || data_values)

mapping_hash = H(source_table || source_column || target_table ||
                 target_column || transform_fn_signature)

migration_id = H("sqlite_to_pg" || snapshot_hash || mapping_hash ||
                 target_schema_version)
```

Where `H()` is SHA-256 and `||` is sorted-key canonical JSON concatenation.

### Migration Guard Table

| Condition | Pass | Fail |
|-----------|------|------|
| snapshot_hash from extract matches expected | ✅ | ❌ Block — source data changed mid-migration |
| mapping_hash is deterministic (same rules → same hash) | ✅ | ❌ Block — non-deterministic mapping |
| target_schema_version is consistent with manifest | ✅ | ❌ Block — schema version mismatch |
| source row_count == expected_row_count | ✅ | ❌ Block — row count drift |
| integrity_pct == 100% after verify | ✅ | ❌ Block — data integrity failure |
| **LAW:** RULE 1 (Determinism), LAW 14 (DAG Integrity) | | |

### Compaction Guard

| Condition | Pass | Fail |
|-----------|------|------|
| retention_sec_elapsed >= policy | ✅ | ❌ Block — retention not met |
| no_active_readers_on_segment | ✅ | ❌ Block — segment in use |
| compacted_segment_hash matches source | ✅ | ❌ Block — corruption detected |
| **LAW:** RULE 5 (Recovery) | | |

---

## ACID Compliance Matrix

| Concern | Guard | Enforcement |
|---------|-------|-------------|
| No tx without isolation level | G2 | Block transition |
| No commit without partition key | G3 | Block transaction |
| No commit without quorum acks | G4 | Wait or rollback |
| No partial commits on failure | G5 | Auto-rollback |
| No infinite deadlock retry | G6 | Max retry cap |
| No tx without data_trace_id | G1, G7 | Block or rollback |
| No replica force-commit | G8 | Block without ack |
| Non-deterministic migration | DGM | Block on checksum mismatch |
| Premature log compaction | CG | Block if segment in use |
