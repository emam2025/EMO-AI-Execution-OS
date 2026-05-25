import os
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from tools import Tool


GITHUB_API = "https://api.github.com"


def _headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    h = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Emo-AI-Agent/1.0",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _gh_request(method, url, data=None):
    import urllib.request
    req = Request(url, data=json.dumps(data).encode() if data else None, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            return {"error": err.get("message", str(e))}
        except Exception:
            return {"error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error": str(e)}


class GitHubCreateRepo(Tool):
    name = "github_create_repo"
    description = "Create a new GitHub repository"
    category = "GitHub"
    icon = "📦"
    parameters = {"repo_name": "string", "description": "string", "private": "boolean"}

    def run(self, repo_name="", description="", private=False):
        if not repo_name:
            return "Error: repo_name is required"
        data = {"name": repo_name, "description": description, "private": bool(private)}
        result = _gh_request("POST", f"{GITHUB_API}/user/repos", data)
        if "error" in result:
            return f"Failed to create repo: {result['error']}"
        clone_url = result.get("clone_url", result.get("html_url", ""))
        return f"Repository created: {result.get('html_url')}\nClone URL: {clone_url}"


class GitHubCloneRepo(Tool):
    name = "github_clone_repo"
    description = "Clone a GitHub repository to local machine"
    category = "GitHub"
    icon = "📥"
    parameters = {"repo_url": "string", "target_dir": "string"}

    def run(self, repo_url="", target_dir=""):
        if not repo_url:
            return "Error: repo_url is required"
        target = Path(target_dir).expanduser().resolve() if target_dir else Path.cwd() / repo_url.split("/")[-1].replace(".git", "")
        if target.exists():
            return f"Directory already exists: {target}"
        token = os.environ.get("GITHUB_TOKEN", "")
        if token and "github.com" in repo_url:
            parsed = repo_url.replace("https://", f"https://{token}@")
            result = subprocess.run(["git", "clone", parsed, str(target)], capture_output=True, text=True, timeout=120)
        else:
            result = subprocess.run(["git", "clone", repo_url, str(target)], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return f"Clone failed: {result.stderr[:500]}"
        return f"Cloned to {target}"


class GitHubPushChanges(Tool):
    name = "github_push_changes"
    description = "Commit and push local changes to GitHub"
    category = "GitHub"
    icon = "⬆️"
    parameters = {"repo_path": "string", "commit_message": "string", "branch": "string"}

    def run(self, repo_path=".", commit_message="Auto-commit by Emo AI", branch="main"):
        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists():
            return f"Not a git repository: {repo}"
        add = subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True, text=True, timeout=30)
        if add.returncode != 0:
            return f"git add failed: {add.stderr[:300]}"
        commit = subprocess.run(["git", "commit", "-m", commit_message], cwd=str(repo), capture_output=True, text=True, timeout=30)
        push = subprocess.run(["git", "push", "origin", branch], cwd=str(repo), capture_output=True, text=True, timeout=60)
        if push.returncode != 0:
            return f"Push failed: {push.stderr[:500]}"
        return f"Committed and pushed to origin/{branch}"


class GitHubPullRepo(Tool):
    name = "github_pull_repo"
    description = "Pull latest changes from GitHub"
    category = "GitHub"
    icon = "⬇️"
    parameters = {"repo_path": "string", "branch": "string"}

    def run(self, repo_path=".", branch="main"):
        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists():
            return f"Not a git repository: {repo}"
        result = subprocess.run(["git", "pull", "origin", branch], cwd=str(repo), capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return f"Pull failed: {result.stderr[:500]}"
        return result.stdout[:1000] or f"Pulled latest from origin/{branch}"


class GitHubReadFile(Tool):
    name = "github_read_file"
    description = "Read a file from a GitHub repo (via raw content API)"
    category = "GitHub"
    icon = "👁️"
    parameters = {"owner": "string", "repo": "string", "path": "string", "branch": "string"}

    def run(self, owner="", repo="", path="", branch="main"):
        if not all([owner, repo, path]):
            return "Error: owner, repo, and path are required"
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        result = _gh_request("GET", url)
        if "error" in result:
            return f"Failed to read: {result['error']}"
        content = result.get("content", "")
        import base64
        try:
            decoded = base64.b64decode(content).decode("utf-8")
            return decoded
        except Exception as e:
            return f"Decode error: {e}"


class GitHubWriteFile(Tool):
    name = "github_write_file"
    description = "Create or update a file in a GitHub repo via API"
    category = "GitHub"
    icon = "✏️"
    parameters = {"owner": "string", "repo": "string", "path": "string", "content": "string", "commit_message": "string", "branch": "string"}

    def run(self, owner="", repo="", path="", content="", commit_message="Update via Emo AI", branch="main"):
        if not all([owner, repo, path, content]):
            return "Error: owner, repo, path, and content are required"
        import base64
        get_url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        existing = _gh_request("GET", get_url)
        sha = existing.get("sha") if "error" not in existing else None
        data = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            data["sha"] = sha
        result = _gh_request("PUT", f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}", data)
        if "error" in result:
            return f"Failed to write file: {result['error']}"
        return f"File written: {result.get('content', {}).get('html_url', path)}"


class GitHubCreateBranch(Tool):
    name = "github_create_branch"
    description = "Create a new branch in a GitHub repo"
    category = "GitHub"
    icon = "🌿"
    parameters = {"owner": "string", "repo": "string", "branch_name": "string", "base_branch": "string"}

    def run(self, owner="", repo="", branch_name="", base_branch="main"):
        if not all([owner, repo, branch_name]):
            return "Error: owner, repo, and branch_name are required"
        ref_url = f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
        ref_result = _gh_request("GET", ref_url)
        if "error" in ref_result:
            return f"Failed to get base ref: {ref_result['error']}"
        sha = ref_result.get("object", {}).get("sha")
        if not sha:
            return "Could not get SHA of base branch"
        data = {"ref": f"refs/heads/{branch_name}", "sha": sha}
        result = _gh_request("POST", f"{GITHUB_API}/repos/{owner}/{repo}/git/refs", data)
        if "error" in result:
            return f"Failed to create branch: {result['error']}"
        return f"Branch '{branch_name}' created from '{base_branch}'"
