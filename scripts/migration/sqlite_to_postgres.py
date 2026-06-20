"""Database Migration Script: SQLite → PostgreSQL (Supabase)

Purpose: Migrate local SQLite database to cloud PostgreSQL
Target: Supabase PostgreSQL 15+
"""

import sqlite3
import os
from typing import List, Dict, Any
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None
    execute_values = None


class DatabaseMigrator:
    """Migrate data from SQLite to PostgreSQL."""

    def __init__(self, sqlite_path: str, postgres_url: str):
        self.sqlite_path = sqlite_path
        self.postgres_url = postgres_url
        self.sqlite_conn = None
        self.postgres_conn = None

    def connect_sqlite(self):
        """Connect to SQLite database."""
        if not os.path.exists(self.sqlite_path):
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row

    def connect_postgres(self):
        """Connect to PostgreSQL database."""
        if psycopg2 is None:
            raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
        self.postgres_conn = psycopg2.connect(self.postgres_url)

    def extract_schema(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract schema from SQLite database.

        Returns:
            Dict mapping table names to column definitions.
        """
        self.connect_sqlite()
        cursor = self.sqlite_conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = cursor.fetchall()

        schema = {}
        for (table_name,) in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col["name"],
                    "type": col["type"],
                    "notnull": col["notnull"],
                    "default": col["dflt_value"],
                    "pk": col["pk"],
                })
            schema[table_name] = columns

        self.sqlite_conn.close()
        return schema

    def map_sqlite_type_to_postgres(self, sqlite_type: str) -> str:
        """Map SQLite type to PostgreSQL type."""
        type_mapping = {
            "INTEGER": "BIGINT",
            "TEXT": "TEXT",
            "REAL": "DOUBLE PRECISION",
            "BLOB": "BYTEA",
            "NUMERIC": "NUMERIC",
            "BOOLEAN": "BOOLEAN",
            "DATETIME": "TIMESTAMP WITH TIME ZONE",
            "DATE": "DATE",
            "TIME": "TIME WITH TIME ZONE",
        }
        return type_mapping.get(sqlite_type.upper(), "TEXT")

    def create_postgres_schema(self, schema: Dict[str, List[Dict[str, Any]]]):
        """Create equivalent schema in PostgreSQL.

        Args:
            schema: Extracted SQLite schema.
        """
        self.connect_postgres()
        cursor = self.postgres_conn.cursor()

        for table_name, columns in schema.items():
            # Build CREATE TABLE statement
            col_defs = []
            for col in columns:
                pg_type = self.map_sqlite_type_to_postgres(col["type"])
                col_def = f"  {col['name']} {pg_type}"
                if col["pk"]:
                    col_def += " PRIMARY KEY"
                elif col["notnull"]:
                    col_def += " NOT NULL"
                if col["default"]:
                    col_def += f" DEFAULT {col['default']}"
                col_defs.append(col_def)

            create_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(col_defs)}
            );
            """
            cursor.execute(create_sql)

        self.postgres_conn.commit()
        self.postgres_conn.close()

    def migrate_data(self, table_name: str):
        """Migrate data from SQLite table to PostgreSQL.

        Args:
            table_name: Name of the table to migrate.
        """
        self.connect_sqlite()
        self.connect_postgres()

        # Read from SQLite
        sqlite_cursor = self.sqlite_conn.cursor()
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()

        if not rows:
            print(f"  ℹ️  No data in table: {table_name}")
            return

        # Get column names
        column_names = [desc[0] for desc in sqlite_cursor.description]

        # Write to PostgreSQL
        pg_cursor = self.postgres_conn.cursor()

        # Build INSERT statement
        insert_sql = f"""
        INSERT INTO {table_name} ({', '.join(column_names)})
        VALUES %s
        ON CONFLICT DO NOTHING
        """

        # Convert rows to list of tuples
        data = [tuple(row) for row in rows]

        # Batch insert
        execute_values(pg_cursor, insert_sql, data, page_size=1000)
        self.postgres_conn.commit()

        print(f"  ✅ Migrated {len(data)} rows to {table_name}")

        self.sqlite_conn.close()
        self.postgres_conn.close()

    def verify_migration(self) -> bool:
        """Verify data integrity after migration.

        Returns:
            True if verification passed, False otherwise.
        """
        self.connect_sqlite()
        self.connect_postgres()

        sqlite_cursor = self.sqlite_conn.cursor()
        pg_cursor = self.postgres_conn.cursor()

        # Get all tables
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in sqlite_cursor.fetchall()]

        all_passed = True
        for table_name in tables:
            # Count rows in SQLite
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = sqlite_cursor.fetchone()[0]

            # Count rows in PostgreSQL
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            pg_count = pg_cursor.fetchone()[0]

            if sqlite_count == pg_count:
                print(f"  ✅ {table_name}: {sqlite_count} rows (matched)")
            else:
                print(f"  ❌ {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count} (MISMATCH)")
                all_passed = False

        self.sqlite_conn.close()
        self.postgres_conn.close()

        return all_passed


def main():
    """Main migration entry point."""
    sqlite_path = os.getenv("SQLITE_PATH", "emo_ai.db")
    postgres_url = os.getenv("DATABASE_URL")

    if not postgres_url:
        print("❌ DATABASE_URL environment variable not set")
        print("   Set it to your Supabase PostgreSQL connection string")
        print("   Example: export DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
        return

    print(f"🚀 Starting migration: SQLite → PostgreSQL")
    print(f"   SQLite: {sqlite_path}")
    print(f"   PostgreSQL: {postgres_url[:30]}...")
    print()

    migrator = DatabaseMigrator(sqlite_path, postgres_url)

    # Step 1: Extract schema
    print("📋 Step 1: Extracting schema from SQLite...")
    try:
        schema = migrator.extract_schema()
        print(f"   Found {len(schema)} tables")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    # Step 2: Create PostgreSQL schema
    print("\n🔧 Step 2: Creating PostgreSQL schema...")
    try:
        migrator.create_postgres_schema(schema)
        print("   ✅ Schema created")
    except Exception as e:
        print(f"   ❌ Error creating schema: {e}")
        return

    # Step 3: Migrate data
    print("\n📦 Step 3: Migrating data...")
    try:
        for table_name in schema.keys():
            migrator.migrate_data(table_name)
    except Exception as e:
        print(f"   ❌ Error migrating data: {e}")
        return

    # Step 4: Verify
    print("\n🔍 Step 4: Verifying migration...")
    if migrator.verify_migration():
        print("\n✅ Migration successful!")
    else:
        print("\n❌ Migration verification failed!")


if __name__ == "__main__":
    main()
