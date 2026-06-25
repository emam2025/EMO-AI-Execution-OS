# Database Migration: SQLite → PostgreSQL

> Database migration guide from local SQLite to cloud PostgreSQL

---

## Overview

This directory contains scripts to migrate the EMO AI database from local SQLite to cloud PostgreSQL (Supabase).

## Prerequisites

- Python 3.14+
- PostgreSQL 15+ (Supabase)
- `psycopg2` library: `pip install psycopg2-binary`

## Usage

### 1. Set Environment Variables

```bash
export SQLITE_PATH="emo_ai.db"
export DATABASE_URL="postgresql://user:password@host:port/dbname"
```

### 2. Run Migration

```bash
python scripts/migration/sqlite_to_postgres.py
```

### 3. Verify Migration

The script will automatically verify data integrity after migration.

### 4. Rollback

If migration fails, the original SQLite database remains unchanged.

## Next Steps

After successful migration:

1. Update `core/db.py` to use PostgreSQL connection
2. Update `.env` with `DATABASE_URL`
3. Test all CRUD operations
4. Deploy to Supabase

## Files

| File | Description |
|------|-------------|
| `sqlite_to_postgres.py` | Main migration script |
| `schema_mapping.json` | Type and table mappings |
| `README.md` | This file |

## Troubleshooting

### Connection Issues

```bash
# Test PostgreSQL connection
psql $DATABASE_URL

# Check if database exists
psql -c "\l" | grep emo_ai
```

### Permission Issues

```bash
# Grant permissions
GRANT ALL PRIVILEGES ON DATABASE emo_ai TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

---

**Last Updated:** 2026-06-12
