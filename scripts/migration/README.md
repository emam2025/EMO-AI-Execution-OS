# Database Migration: SQLite → PostgreSQL

> Guide for migrating the database from local SQLite to cloud PostgreSQL

---

## Overview

This directory contains scripts to migrate the EMO AI database from local SQLite to cloud PostgreSQL (Supabase).

## Prerequisites

- Python 3.12+
- PostgreSQL 15+ (Supabase)
- `psycopg2` library: `pip install psycopg2-binary`

## Usage

### 1. Set Environment Variables

```bash
export DATABASE_URL="postgresql://user:password@host:port/database"
```

### 2. Run Migration

```bash
python3 scripts/migration/migrate.py
```

### 3. Verify

```bash
python3 -c "
import asyncio
from core.db import db
asyncio.run(db.initialize())
print('Migration complete')
"
```

---

## Notes

- Always backup your SQLite database before migration
- Test migration on a copy first
- The migration script handles schema translation automatically
- All `?` placeholders are translated to `$N` PostgreSQL format
- `datetime('now')` is translated to `NOW()`
