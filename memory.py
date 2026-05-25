from typing import Dict, List, Optional
from datetime import datetime


class Memory:
    """Short-term and long-term memory for EMO AI agents.

    Short-term: in-memory conversation context.
    Long-term: persistent storage via SQLite (post-MVP with vector embeddings).
    """

    def __init__(self):
        self.data: List[Dict] = []
        self._max_entries = 1000

    def add(self, entry: Dict) -> None:
        """Add a memory entry."""
        entry["timestamp"] = datetime.utcnow().isoformat()
        self.data.append(entry)
        # Trim if too large
        if len(self.data) > self._max_entries:
            self.data = self.data[-self._max_entries:]

    def get(self, limit: int = 10) -> List[Dict]:
        """Get recent memory entries."""
        return self.data[-limit:]

    def search(self, query: str) -> List[Dict]:
        """Simple keyword search in memory entries."""
        results = []
        query_lower = query.lower()
        for entry in self.data:
            content = entry.get("content", "").lower()
            if query_lower in content:
                results.append(entry)
        return results

    def clear(self) -> None:
        """Clear all memory."""
        self.data = []

    def __len__(self) -> int:
        return len(self.data)
