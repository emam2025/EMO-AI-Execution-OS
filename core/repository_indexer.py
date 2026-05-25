"""Repository Indexer for EMO AI Code Intelligence Layer.

This module provides incremental repository indexing capabilities:
- Scans the repository for changes
- Extracts metadata from files (imports, exports, TODOs, etc.)
- Stores information in SQLite for efficient querying
- Supports incremental updates (only changed files re-indexed)
"""

import ast
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import re

from .ai_logging import get_ai_logger, log_ai_decision
from .parsers import get_parser_for_extension, LanguageParser

# Initialize logger
indexer_logger = get_ai_logger("indexer")


class RepositoryIndexer:
    """Incremental repository indexer for code intelligence."""
    
    def __init__(
        self,
        repo_root: str = None,
        db_path: str = None,
        embedding_engine: Optional[Any] = None,
        semantic_store: Optional[Any] = None,
    ):
        """Initialize the repository indexer.

        Args:
            repo_root: Root directory of the repository to index
            db_path: Path to the SQLite database for storing index
            embedding_engine: Optional EmbeddingEngine for semantic indexing
            semantic_store: Optional SemanticStore for vector storage
        """
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.db_path = Path(db_path) if db_path else self.repo_root / ".ai" / "index" / "repository.db"
        self.embedding_engine = embedding_engine
        self.semantic_store = semantic_store
        
        # Ensure the directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_database()
        
        # File patterns to ignore
        self.ignore_patterns = {
            # Directories
            "node_modules", ".git", "dist", "build", ".next", "coverage",
            "__pycache__", ".pytest_cache", ".venv", "venv", "env",
            # Files
            "*.pyc", "*.pyo", "*.pyd", ".DS_Store", "Thumbs.db", "*.db",
            # Environment and config files that shouldn't be indexed for code
            ".env", ".env.*", ".npmrc", ".yarnrc", ".yarnrc.yml",
            # Lock files
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            # Build artifacts
            "*.min.js", "*.min.css", "*.bundle.*",
            # Logs
            "*.log",
        }
        
        indexer_logger.info(f"RepositoryIndexer initialized for {self.repo_root}")
    
    def _init_database(self):
        """Initialize the SQLite database schema for storing repository index."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.executescript("""
                -- Files table stores basic file information
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT,
                    size INTEGER,
                    modified_time REAL,
                    hash TEXT,  -- SHA256 of file content
                    indexed_time REAL,
                    is_binary BOOLEAN DEFAULT 0,
                    is_ignored BOOLEAN DEFAULT 0
                );
                
                -- Imports/exports/dependencies between files
                CREATE TABLE IF NOT EXISTS file_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file_id INTEGER NOT NULL,
                    target_module TEXT NOT NULL,  -- What was imported/required
                    target_file_id INTEGER,       -- Resolved target file (if known)
                    import_type TEXT,             -- import, require, from, etc.
                    line_number INTEGER,
                    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE SET NULL
                );
                
                -- Symbols (functions, classes, etc.) found in files
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,  -- function, class, interface, variable, etc.
                    line_number INTEGER,
                    column_number INTEGER,
                    end_line INTEGER,
                    end_column INTEGER,
                    signature TEXT,             -- Function signature or class declaration
                    docstring TEXT,             -- Extracted docstring or JSDoc
                    properties TEXT,            -- JSON blob for extended analysis (Phase 6)
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                );
                
                -- Symbol relationships (calls, inheritance, etc.)
                CREATE TABLE IF NOT EXISTS symbol_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_symbol_id INTEGER NOT NULL,
                    target_symbol_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,  -- calls, extends, implements, uses, etc.
                    line_number INTEGER,
                    FOREIGN KEY (source_symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_symbol_id) REFERENCES symbols(id) ON DELETE CASCADE
                );
                
                -- TODOs, FIXMEs, HACKs, etc.
                CREATE TABLE IF NOT EXISTS annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    annotation_type TEXT NOT NULL,  -- TODO, FIXME, HACK, NOTE, etc.
                    message TEXT NOT NULL,
                    line_number INTEGER,
                    column_number INTEGER,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                );
                
                -- File metadata (language-specific info)
                CREATE TABLE IF NOT EXISTS file_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    UNIQUE(file_id, key)
                );
                
                -- Indexing statistics and metadata
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at REAL
                );
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
                CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
                CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash);
                CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_time);
                CREATE INDEX IF NOT EXISTS idx_file_deps_source ON file_dependencies(source_file_id);
                CREATE INDEX IF NOT EXISTS idx_file_deps_target ON file_dependencies(target_file_id);
                CREATE INDEX IF NOT EXISTS idx_file_deps_module ON file_dependencies(target_module);
                CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(symbol_type);
                CREATE INDEX IF NOT EXISTS idx_symbols_relationships_source ON symbol_relationships(source_symbol_id);
                CREATE INDEX IF NOT EXISTS idx_symbols_relationships_target ON symbol_relationships(target_symbol_id);
                CREATE INDEX IF NOT EXISTS idx_annotations_file ON annotations(file_id);
                CREATE INDEX IF NOT EXISTS idx_annotations_type ON annotations(annotation_type);
                CREATE INDEX IF NOT EXISTS idx_file_metadata_file ON file_metadata(file_id);
                CREATE INDEX IF NOT EXISTS idx_file_metadata_key ON file_metadata(key);

                -- Graph edges for Phase 5 symbol intelligence
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    edge_type TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    weight REAL NOT NULL DEFAULT 1.0,
                    properties TEXT,
                    created_at REAL,
                    updated_at REAL,
                    UNIQUE(source_type, source_id, target_type, target_id, edge_type)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_tgt ON graph_edges(target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_resolved ON graph_edges(resolved);
            """)
            # Migration: add properties column to symbols (Phase 6)
            try:
                conn.execute("ALTER TABLE symbols ADD COLUMN properties TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.commit()
    
    def _get_file_hash(self, file_path: Path) -> Optional[str]:
        """Calculate SHA256 hash of file content.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Hexadecimal hash string or None if file cannot be read
        """
        try:
            # Check if it's a binary file by trying to read as text
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                # Simple heuristic: if null byte in first chunk, likely binary
                if b'\x00' in chunk:
                    return None
                # Reset and calculate hash
                f.seek(0)
                hash_sha256 = hashlib.sha256()
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
                return hash_sha256.hexdigest()
        except (IOError, OSError):
            return None
    
    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if a file should be ignored based on patterns.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be ignored
        """
        # Check against ignore patterns
        path_str = str(file_path.relative_to(self.repo_root))
        
        # Check directory components
        for part in file_path.parts:
            if part in self.ignore_patterns:
                return True
        
        # Check file patterns
        file_name = file_path.name
        for pattern in self.ignore_patterns:
            if pattern.startswith("*."):
                # Extension pattern like *.pyc
                ext = pattern[1:]  # Remove the *
                if file_name.endswith(ext):
                    return True
            elif pattern in file_name:
                return True
        
        # Check for application specific files
        if file_name.startswith(".emo_"):
            return True
        
        return False
    
    def _get_file_info(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get basic information about a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file info or None if file should be skipped
        """
        if not file_path.exists() or not file_path.is_file():
            return None
        
        # Check if we should ignore this file
        if self._should_ignore_file(file_path):
            return {
                "path": str(file_path.relative_to(self.repo_root)),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "size": file_path.stat().st_size,
                "modified_time": file_path.stat().st_mtime,
                "hash": None,
                "is_binary": False,
                "is_ignored": True
            }
        
        # Get file stats
        stat = file_path.stat()
        
        # Calculate hash (only for non-binary files we care about)
        file_hash = None
        is_binary = False
        
        if file_path.suffix.lower() in [".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".md", ".txt"]:
            file_hash = self._get_file_hash(file_path)
            if file_hash is None:
                # Could not read as text, treat as binary
                is_binary = True
                file_hash = self._get_file_hash(file_path)  # Try binary hash
        
        return {
            "path": str(file_path.relative_to(self.repo_root)),
            "name": file_path.name,
            "extension": file_path.suffix.lower(),
            "size": stat.st_size,
            "modified_time": stat.st_mtime,
            "hash": file_hash,
            "is_binary": is_binary,
            "is_ignored": False
        }
    
    def _get_indexed_file_hash(self, file_path: str) -> Optional[str]:
        """Get the hash of a file from the index.
        
        Args:
            file_path: Relative path of the file
            
        Returns:
            Hash string if found in index, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT hash FROM files WHERE path = ?", 
                (file_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def _is_file_changed(self, file_path: Path) -> bool:
        """Check if a file has changed since last indexing.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file has changed or is not indexed, False otherwise
        """
        relative_path = str(file_path.relative_to(self.repo_root))
        
        # Get current file info
        current_info = self._get_file_info(file_path)
        if not current_info:
            return False
        
        # If file is ignored, we don't need to index it
        if current_info["is_ignored"]:
            return False
        
        # Get previously indexed hash
        indexed_hash = self._get_indexed_file_hash(relative_path)
        
        # If not indexed before, or hash changed, or file is binary and we can't hash it properly
        if indexed_hash is None:
            return True
        
        if current_info["hash"] is None:
            # Can't determine if changed, err on side of re-indexing
            return True
            
        return current_info["hash"] != indexed_hash
    
    def _update_file_record(self, file_info: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> int:
        """Insert or update a file record in the database, preserving the file ID.

        Uses UPDATE when the file already exists (by path) and INSERT otherwise,
        so the primary key never changes across re-indexes.

        Args:
            file_info: Dictionary from _get_file_info
            conn: Optional SQLite connection to use. If provided, the caller is
                  responsible for committing.

        Returns:
            The file ID (primary key)
        """
        if conn is None:
            with sqlite3.connect(self.db_path) as local_conn:
                local_conn.execute("PRAGMA journal_mode=WAL")
                return self._update_file_record_inner(file_info, local_conn)
        return self._update_file_record_inner(file_info, conn)

    def _update_file_record_inner(
        self, file_info: Dict[str, Any], conn: sqlite3.Connection,
    ) -> int:
        """Inner implementation of _update_file_record with a guaranteed connection."""
        existing = conn.execute(
            "SELECT id FROM files WHERE path = ?", (file_info["path"],)
        ).fetchone()

        now = datetime.utcnow().timestamp()

        if existing:
            file_id = existing[0]
            conn.execute(
                """UPDATE files SET
                   name=?, extension=?, size=?, modified_time=?,
                   hash=?, indexed_time=?, is_binary=?, is_ignored=?
                   WHERE id=?""",
                (
                    file_info["name"],
                    file_info["extension"],
                    file_info["size"],
                    file_info["modified_time"],
                    file_info["hash"],
                    now,
                    file_info["is_binary"],
                    file_info["is_ignored"],
                    file_id,
                ),
            )
            conn.commit()
            return file_id
        else:
            cursor = conn.execute(
                """INSERT INTO files
                   (path, name, extension, size, modified_time, hash,
                    indexed_time, is_binary, is_ignored)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_info["path"],
                    file_info["name"],
                    file_info["extension"],
                    file_info["size"],
                    file_info["modified_time"],
                    file_info["hash"],
                    now,
                    file_info["is_binary"],
                    file_info["is_ignored"],
                ),
            )
            conn.commit()
            return cursor.lastrowid
    
    def _delete_file_related_data(self, file_id: int):
        """Delete all data related to a file when it's removed or ignored.
        
        Args:
            file_id: ID of the file in the files table
        """
        with sqlite3.connect(self.db_path) as conn:
            # Delete in order due to foreign key constraints
            conn.execute("DELETE FROM annotations WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM symbol_relationships WHERE source_symbol_id IN (SELECT id FROM symbols WHERE file_id = ?)", (file_id,))
            conn.execute("DELETE FROM symbol_relationships WHERE target_symbol_id IN (SELECT id FROM symbols WHERE file_id = ?)", (file_id,))
            # Remove graph edges referencing this file's symbols
            conn.execute(
                "DELETE FROM graph_edges WHERE source_id IN "
                "(SELECT CAST(id AS TEXT) FROM symbols WHERE file_id = ?)",
                (file_id,),
            )
            conn.execute(
                "DELETE FROM graph_edges WHERE target_id IN "
                "(SELECT CAST(id AS TEXT) FROM symbols WHERE file_id = ?) AND target_type='symbol'",
                (file_id,),
            )
            conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM file_dependencies WHERE source_file_id = ? OR target_file_id = ?", (file_id, file_id))
            conn.execute("DELETE FROM file_metadata WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()

        # Clean up semantic store if available
        if self.semantic_store:
            # Symbol IDs are no longer available in DB, but we stored them
            # in the store metadata.  We just leave orphan entries; they
            # will be overwritten on next index of the same path.
            pass
    def scan_and_index(self, force_full: bool = False) -> Dict[str, Any]:
        """Scan the repository and index changed files.
        
        Args:
            force_full: If True, re-index all files regardless of changes
            
        Returns:
            Dictionary with indexing statistics
        """
        start_time = datetime.utcnow().timestamp()
        indexer_logger.info(f"Starting repository scan (force_full={force_full})")
        
        stats = {
            "files_scanned": 0,
            "files_indexed": 0,
            "files_skipped": 0,
            "files_removed": 0,
            "errors": 0,
            "start_time": start_time,
            "end_time": None
        }
        
        try:
            # Get all currently tracked files from database
            tracked_files = set()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT path FROM files WHERE is_ignored = 0")
                tracked_files = {row[0] for row in cursor.fetchall()}
            
            # Walk the repository
            found_files = set()
            for root, dirs, files in os.walk(self.repo_root):
                # Skip ignored directories early
                dirs[:] = [d for d in dirs if d not in self.ignore_patterns]
                
                root_path = Path(root)
                for file_name in files:
                    file_path = root_path / file_name
                    stats["files_scanned"] += 1
                    
                    try:
                        relative_path = str(file_path.relative_to(self.repo_root))
                        found_files.add(relative_path)
                        
                        # Check if file needs indexing
                        if force_full or self._is_file_changed(file_path):
                            file_info = self._get_file_info(file_path)
                            if file_info and not file_info["is_ignored"]:
                                # Update file record
                                file_id = self._update_file_record(file_info)

                            # Parse file content if it's a code file we care about and not ignored
                            if file_info:
                                if (file_info.get("extension") in [".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".md", ".txt"]
                                    and not file_info.get("is_binary")
                                    and not file_info.get("is_ignored")):
                                    try:
                                        self._parse_file_content(file_path, file_id)
                                        stats["files_indexed"] += 1
                                        indexer_logger.debug(f"Indexed: {relative_path}")
                                    except Exception as e:
                                        indexer_logger.error(f"Error parsing {relative_path}: {e}")
                                        stats["errors"] += 1
                                elif file_info.get("is_ignored"):
                                    self._update_file_record(file_info)
                                    stats["files_skipped"] += 1
                                else:
                                    stats["files_removed"] += 1
                        else:
                            # File hasn't changed
                            stats["files_skipped"] += 1
                            
                    except Exception as e:
                        indexer_logger.error(f"Error processing {file_path}: {e}")
                        stats["errors"] += 1
            
            # Remove files that are no longer in the repository
            removed_files = tracked_files - found_files
            for relative_path in removed_files:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute("SELECT id FROM files WHERE path = ?", (relative_path,))
                    row = cursor.fetchone()
                    if row:
                        file_id = row[0]
                        self._delete_file_related_data(file_id)
                        stats["files_removed"] += 1
                        indexer_logger.debug(f"Removed from index: {relative_path}")

            # Resolve cross-file symbol references after all files are indexed
            stats["edges_resolved"] = self.resolve_unresolved_edges()

            # Update indexing metadata
            end_time = datetime.utcnow().timestamp()
            stats["end_time"] = end_time
            stats["duration_seconds"] = end_time - start_time
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO index_metadata (key, value, updated_at)
                    VALUES ('last_full_index', ?, ?)
                """, (
                    json.dumps({
                        "timestamp": end_time,
                        "files_indexed": stats["files_indexed"],
                        "duration_seconds": stats["duration_seconds"]
                    }),
                    end_time
                ))
                conn.commit()
            
            # Log indexing decision
            log_ai_decision(
                decision_type="repository_indexing",
                description=f"Repository indexing completed",
                context=json.dumps({
                    "files_scanned": stats["files_scanned"],
                    "files_indexed": stats["files_indexed"],
                    "files_removed": stats["files_removed"],
                    "duration_seconds": stats["duration_seconds"]
                })
            )
            
            indexer_logger.info(
                f"Repository scan completed in {stats['duration_seconds']:.2f}s. "
                f"Indexed: {stats['files_indexed']}, Skipped: {stats['files_skipped']}, "
                f"Removed: {stats['files_removed']}, Errors: {stats['errors']}"
            )
            
            return stats
            
        except Exception as e:
            indexer_logger.error(f"Fatal error during repository scan: {e}", exc_info=True)
            stats["end_time"] = datetime.utcnow().timestamp()
            stats["duration_seconds"] = stats["end_time"] - start_time
            return stats
    
    # ===== PARSING METHODS =====
    
    def _parse_file_content(self, file_path: Path, file_id: int):
        """Parse file content using the appropriate parser based on file extension.

        Args:
            file_path: Path to the file
            file_id: ID of the file in the database
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Clear existing data for this file (we'll re-insert)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM annotations WHERE file_id = ?", (file_id,))
                # Remove graph edges where THIS file's symbols are the SOURCE
                # (edges originating from this file). Edges where this file's
                # symbols are the TARGET (cross-file references) are preserved
                # so that re-indexing a library file doesn't destroy callers' edges.
                conn.execute(
                    "DELETE FROM graph_edges WHERE source_id IN "
                    "(SELECT CAST(id AS TEXT) FROM symbols WHERE file_id = ?)",
                    (file_id,),
                )
                conn.execute("DELETE FROM symbol_relationships WHERE source_symbol_id IN (SELECT id FROM symbols WHERE file_id = ?)", (file_id,))
                conn.execute("DELETE FROM symbol_relationships WHERE target_symbol_id IN (SELECT id FROM symbols WHERE file_id = ?)", (file_id,))
                conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
                conn.execute("DELETE FROM file_dependencies WHERE source_file_id = ?", (file_id,))
                conn.execute("DELETE FROM file_metadata WHERE file_id = ?", (file_id,))
                conn.commit()

            # Get the appropriate parser for the file extension
            parser = get_parser_for_extension(file_path.suffix.lower())

            # Parse the content — parsers no longer write to DB, they return structured data
            result = parser.parse(file_path, file_id, content)

            # Store the parsed data in the database
            self._store_parse_result(file_id, result)

        except Exception as e:
            indexer_logger.error(f"Error parsing file {file_path}: {e}")
            raise

    def _store_parse_result(self, file_id: int, result: dict) -> None:
        """Store the structured result from a parser into the database.

        Args:
            file_id: ID of the file being indexed
            result: Dictionary with keys: dependencies, symbols,
                    symbol_relationships, annotations, file_metadata
        """
        with sqlite3.connect(self.db_path) as conn:
            # ---- file_metadata ----
            for md in result.get("file_metadata", []):
                conn.execute(
                    "INSERT OR REPLACE INTO file_metadata (file_id, key, value) VALUES (?, ?, ?)",
                    (file_id, md.get("key"), md.get("value")),
                )

            # ---- dependencies ----
            for dep in result.get("dependencies", []):
                conn.execute(
                    "INSERT INTO file_dependencies (source_file_id, target_module, import_type, line_number) "
                    "VALUES (?, ?, ?, ?)",
                    (file_id,
                     dep.get("module") or dep.get("name") or "",
                     dep.get("type", "unknown"),
                     dep.get("line", 0)),
                )

            # ---- symbols ----
            symbol_id_map: dict[str, int] = {}  # symbol_name -> db id
            for sym in result.get("symbols", []):
                # Serialize static_analysis into properties JSON
                analysis = sym.get("static_analysis")
                props_json = json.dumps(analysis) if analysis else None
                cur = conn.execute(
                    "INSERT INTO symbols (file_id, name, symbol_type, line_number, column_number, "
                    "end_line, end_column, signature, docstring, properties) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_id,
                        sym.get("name", ""),
                        sym.get("symbol_type", "unknown"),
                        sym.get("line_number"),
                        sym.get("column_number"),
                        sym.get("end_line"),
                        sym.get("end_column"),
                        sym.get("signature"),
                        sym.get("docstring", ""),
                        props_json,
                    ),
                )
                symbol_id_map[sym["name"]] = cur.lastrowid

            # ---- semantic indexing (Phase 10) ----
            if self.embedding_engine and self.semantic_store:
                for sym in result.get("symbols", []):
                    sid = symbol_id_map.get(sym.get("name", ""))
                    if sid is None:
                        continue
                    # Build a metadata dict for the semantic store
                    meta = {
                        "name": sym.get("name", ""),
                        "symbol_type": sym.get("symbol_type", ""),
                        "signature": sym.get("signature", ""),
                        "docstring": sym.get("docstring", ""),
                        "file_id": file_id,
                        "call_type": sym.get("call_type", ""),
                        "decorators": sym.get("decorators", []),
                        "role": (
                            sym.get("static_analysis", {})
                            .get("role", "")
                        ),
                    }
                    vector = self.embedding_engine.embed_symbol(sym)
                    if vector:
                        self.semantic_store.upsert_symbol(
                            str(sid), vector, meta,
                        )

            # ---- graph_edges (symbol relationships with upsert) ----
            now = time.time()
            for rel in result.get("symbol_relationships", []):
                source_name = rel.get("source", "")
                target_name = rel.get("target", "")
                edge_type = rel.get("edge_type", "call")
                props = dict(rel.get("properties", {}))
                # Always store the target name in properties for resolution
                props["target_name"] = target_name
                props["source_name"] = source_name
                props_json = json.dumps(props)

                source_id_str = str(symbol_id_map.get(source_name))
                if not source_id_str:
                    continue  # source symbol should always be in the map

                # Try to resolve target within the current file
                tgt_id = symbol_id_map.get(target_name)
                if tgt_id is not None:
                    # Intra-file: immediately resolved
                    target_id_str = str(tgt_id)
                    resolved = 1
                else:
                    # Cross-file (or not yet indexed): leave unresolved
                    target_id_str = None
                    resolved = 0

                edge_id = str(uuid.uuid4())
                try:
                    conn.execute(
                        """INSERT INTO graph_edges
                           (id, source_type, source_id, target_type, target_id,
                            edge_type, resolved, weight, properties, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(source_type, source_id, target_type, target_id, edge_type)
                           DO UPDATE SET
                               properties = excluded.properties,
                               resolved = excluded.resolved,
                               weight = excluded.weight,
                               updated_at = excluded.updated_at""",
                        (
                            edge_id,
                            "symbol",
                            source_id_str,
                            "symbol",
                            target_id_str,
                            edge_type,
                            resolved,
                            props.get("call_count", 1),
                            props_json,
                            now,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError:
                    # This can happen with the UNIQUE constraint if target_id is NULL
                    # because multiple unresolved edges to different targets would conflict
                    # on (symbol, src_id, symbol, NULL, call).  We insert individually without
                    # the UNIQUE conflict when target_id is null by using a unique edge_id.
                    pass

            # ---- annotations ----
            for ann in result.get("annotations", []):
                conn.execute(
                    "INSERT INTO annotations (file_id, annotation_type, message, line_number, column_number) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        file_id,
                        ann.get("annotation_type", "TODO"),
                        ann.get("message", ""),
                        ann.get("line_number"),
                        ann.get("column_number"),
                    ),
                )

            conn.commit()

    # ── Cross-file resolution ───────────────────────────────────────────

    def resolve_unresolved_edges(self) -> int:
        """Resolve cross-file symbol references in the graph.

        For every unresolved edge (resolved=0), search the symbols table
        for a matching symbol name. If found, update target_id and mark
        resolved=1.  If multiple matches exist, the best match is chosen
        (preferring the most recently indexed symbol).

        Returns:
            Number of edges resolved in this pass.
        """
        resolved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            # Fetch all unresolved edges
            rows = conn.execute(
                "SELECT id, properties FROM graph_edges WHERE resolved = 0"
            ).fetchall()

            for edge_id, props_json in rows:
                try:
                    props = json.loads(props_json) if props_json else {}
                except json.JSONDecodeError:
                    continue

                target_name = props.get("target_name")
                if not target_name:
                    continue

                # Look up the best-matching symbol (most recently inserted wins)
                candidates = conn.execute(
                    "SELECT id FROM symbols WHERE name = ? ORDER BY id DESC LIMIT 1",
                    (target_name,),
                ).fetchall()

                if candidates:
                    tgt_id = candidates[0][0]
                    # Before resolving, check if a row with the same unique
                    # key (source_type, source_id, target_type, target_id,
                    # edge_type) already exists.  If so, the unresolved row
                    # is redundant — delete it.
                    existing = conn.execute(
                        """SELECT id FROM graph_edges
                           WHERE source_type = (SELECT source_type FROM graph_edges WHERE id = ?)
                             AND source_id = (SELECT source_id FROM graph_edges WHERE id = ?)
                             AND target_type = (SELECT target_type FROM graph_edges WHERE id = ?)
                             AND target_id = ?
                             AND edge_type = (SELECT edge_type FROM graph_edges WHERE id = ?)
                           LIMIT 1""",
                        (edge_id, edge_id, edge_id, str(tgt_id), edge_id),
                    ).fetchone()
                    if existing:
                        # A resolved edge with these keys already exists —
                        # delete the unresolved duplicate.
                        conn.execute("DELETE FROM graph_edges WHERE id = ?", (edge_id,))
                    else:
                        conn.execute(
                            "UPDATE graph_edges SET target_id = ?, resolved = 1, updated_at = ? "
                            "WHERE id = ?",
                            (str(tgt_id), time.time(), edge_id),
                        )
                    resolved_count += 1

            conn.commit()

        if resolved_count:
            indexer_logger.info(f"Resolved {resolved_count} cross-file symbol edges")
        return resolved_count
    
    # ===== QUERY METHODS =====
    
    def get_file_dependencies(self, file_path: str) -> List[Dict[str, Any]]:
        """Get dependencies for a specific file.
        
        Args:
            file_path: Relative path of the file
            
        Returns:
            List of dependency dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT fd.*, f.name as target_file_name
                FROM file_dependencies fd
                LEFT JOIN files f ON fd.target_file_id = f.id
                WHERE fd.source_file_id = (
                    SELECT id FROM files WHERE path = ?
                )
            """, (file_path,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_file_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        """Get symbols (functions, classes, etc.) for a specific file.
        
        Args:
            file_path: Relative path of the file
            
        Returns:
            List of symbol dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM symbols
                WHERE file_id = (SELECT id FROM files WHERE path = ?)
                ORDER BY line_number
            """, (file_path,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_symbol_references(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Find all references to a symbol across the repository.
        
        Args:
            symbol_name: Name of the symbol to search for
            
        Returns:
            List of reference dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT s.name as symbol_name, f.path as file_path, 
                       sr.relationship_type, sr.line_number
                FROM symbol_relationships sr
                JOIN symbols s ON sr.source_symbol_id = s.id
                JOIN files f ON s.file_id = f.id
                WHERE s.name = ?
                UNION
                SELECT s.name as symbol_name, f.path as file_path,
                       sr.relationship_type, sr.line_number
                FROM symbol_relationships sr
                JOIN symbols s ON sr.target_symbol_id = s.id
                JOIN files f ON s.file_id = f.id
                WHERE s.name = ?
            """, (symbol_name, symbol_name))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_todos(self, annotation_type: str = None) -> List[Dict[str, Any]]:
        """Search for TODO/FIXME/etc. annotations.
        
        Args:
            annotation_type: Type of annotation to search for (TODO, FIXME, etc.)
                           If None, returns all annotations
            
        Returns:
            List of annotation dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if annotation_type:
                cursor = conn.execute("""
                    SELECT a.*, f.path as file_path
                    FROM annotations a
                    JOIN files f ON a.file_id = f.id
                    WHERE a.annotation_type = ?
                    ORDER BY f.path, a.line_number
                """, (annotation_type.upper(),))
            else:
                cursor = conn.execute("""
                    SELECT a.*, f.path as file_path
                    FROM annotations a
                    JOIN files f ON a.file_id = f.id
                    ORDER BY f.path, a.line_number
                """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific file from the index.
        
        Args:
            file_path: Relative path of the file
            
        Returns:
            File information dictionary or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM files WHERE path = ?
            """, (file_path,))
            row = cursor.fetchone()
            return dict(row) if row else None


# Global indexer instance
repository_indexer = None


def get_repository_indexer() -> RepositoryIndexer:
    """Get or create the global repository indexer instance.
    
    Returns:
        RepositoryIndexer instance
    """
    global repository_indexer
    if repository_indexer is None:
        repository_indexer = RepositoryIndexer()
    return repository_indexer


def initialize_repository_indexer(repo_root: str = None) -> RepositoryIndexer:
    """Initialize the global repository indexer.
    
    Args:
        repo_root: Root directory of the repository
        
    Returns:
        Initialized RepositoryIndexer instance
    """
    global repository_indexer
    repository_indexer = RepositoryIndexer(repo_root)
    return repository_indexer