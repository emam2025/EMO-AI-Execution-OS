interface SearchIndexEntry {
  guide: string;
  title: string;
  content: string;
  path: string;
}

const GUIDES: Array<{ id: string; path: string }> = [
  { id: "user-guide", path: "../guides/user-guide.md" },
  { id: "admin-guide", path: "../guides/admin-guide.md" },
  { id: "security-guide", path: "../guides/security-guide.md" },
  { id: "api-guide", path: "../guides/api-guide.md" },
  { id: "deployment-guide", path: "../guides/deployment-guide.md" },
];

let searchIndex: SearchIndexEntry[] = [];
let searchVisible = false;

async function buildSearchIndex(): Promise<void> {
  for (const guide of GUIDES) {
    try {
      const resp = await fetch(guide.path);
      const text = await resp.text();
      const lines = text.split("\n");
      let currentTitle = guide.id;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const titleMatch = line.match(/^#+\s+(.+)/);
        if (titleMatch) currentTitle = titleMatch[1];
        if (line.trim().length > 20) {
          searchIndex.push({
            guide: guide.id,
            title: currentTitle,
            content: line.trim().slice(0, 200),
            path: guide.path,
          });
        }
      }
    } catch {
      // guide not found, skip
    }
  }
}

function highlight(text: string, query: string): string {
  const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(regex, '<span class="match">$1</span>');
}

function performSearch(query: string): SearchIndexEntry[] {
  const lower = query.toLowerCase();
  return searchIndex
    .filter((e) => e.content.toLowerCase().includes(lower) || e.title.toLowerCase().includes(lower))
    .slice(0, 20);
}

function renderResults(query: string): void {
  const resultsDiv = document.getElementById("searchResults")!;
  const gridDiv = document.getElementById("guideGrid")!;
  if (!query.trim()) {
    resultsDiv.classList.remove("visible");
    resultsDiv.innerHTML = "";
    gridDiv.style.display = "grid";
    return;
  }
  gridDiv.style.display = "none";
  resultsDiv.classList.add("visible");
  const results = performSearch(query);
  if (results.length === 0) {
    resultsDiv.innerHTML = '<div class="no-results">No results found. Try different keywords.</div>';
    return;
  }
  resultsDiv.innerHTML = results
    .map(
      (r) =>
        `<div class="result-item" onclick="window.open('${r.path}', '_blank')">
          <h4>${highlight(r.title, query)}</h4>
          <p>${highlight(r.content, query)}</p>
          <small style="color:#9ca3af;font-size:0.7rem">${r.guide}</small>
        </div>`
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", () => {
  buildSearchIndex();
  const input = document.getElementById("searchInput") as HTMLInputElement;
  if (!input) return;
  input.addEventListener("input", () => renderResults(input.value));
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      input.focus();
    }
    if (e.key === "Escape") {
      input.value = "";
      renderResults("");
      input.blur();
    }
  });
  document.querySelectorAll(".guide-card").forEach((card) => {
    card.addEventListener("click", () => {
      const guide = card.getAttribute("data-guide");
      if (guide) {
        const found = GUIDES.find((g) => g.id === guide);
        if (found) window.open(found.path, "_blank");
      }
    });
  });
});
