import os
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.runtime.data_providers import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    path: str = ""


class ProjectUpdate(BaseModel):
    name: str = ""
    description: str = ""


class SessionCreate(BaseModel):
    name: str = "New Session"


from project_tools import WORKSPACE_ROOT, EMO_AI_PROJECT_DIR


@router.get("")
async def list_projects(archived: bool = False):
    """List all projects (active or archived)."""
    await get_db().initialize()
    projects = await get_db().get_projects(archived=archived)
    active = await get_db().get_active_project()
    return JSONResponse({
        "projects": projects,
        "active_project": active,
    })


@router.post("")
async def create_project(req: ProjectCreate):
    """Create a new project with directory in isolated workspace."""
    await get_db().initialize()

    name = req.name.strip()
    if not name:
        return JSONResponse({"status": "error", "message": "Project name required"})
    if ".." in name or name.startswith("/") or name.startswith("~") or name.startswith("\\") or "/" in name or "\\" in name:
        return JSONResponse({"status": "error", "message": "Invalid project name"})
    if name.startswith("."):
        return JSONResponse({"status": "error", "message": "Project name cannot start with dot"})

    blocked_names = {".env", ".emo_settings.json", "brain.py", "agent.py", "main.py", "emo_ai.db", "requirements.txt"}
    if name.lower() in blocked_names:
        return JSONResponse({"status": "error", "message": "Project name conflicts with system files"})

    custom_path = (req.path or "").strip()
    if custom_path:
        project_path = Path(custom_path).expanduser().resolve()
        if not project_path.is_absolute():
            project_path = (Path.cwd() / project_path).resolve()
    else:
        project_path = WORKSPACE_ROOT / name
    if project_path.exists() and not project_path.is_dir():
        return JSONResponse({"status": "error", "message": "Path exists but is not a directory"})

    existing = await get_db().get_projects()
    for p in existing:
        if p["name"] == name and p["path"] == str(project_path):
            return JSONResponse({"status": "error", "message": "A project with this name and path already exists"})
    if project_path.exists() and any(project_path.iterdir()):
        return JSONResponse({"status": "error", "message": "Directory already exists and is not empty. Pick an empty folder or remove the contents first."})

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        project_id = str(uuid.uuid4())[:8]
        await get_db().create_project(project_id, name, str(project_path), req.description)
        await get_db().activate_project(project_id)

        import json
        settings_file = Path(".emo_settings.json")
        settings = {}
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text())
            except Exception:
                pass
        settings["project_dir"] = str(project_path)
        settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False))

        return JSONResponse({"status": "ok", "id": project_id, "path": str(project_path), "name": name})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@router.post("/{project_id}/activate")
async def activate_project(project_id: str):
    """Set a project as active."""
    await get_db().initialize()
    await get_db().activate_project(project_id)
    project = await get_db().get_active_project()
    if project:
        import json
        settings_file = Path(".emo_settings.json")
        settings = {}
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text())
            except Exception:
                pass
        settings["project_dir"] = project["path"]
        settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    return JSONResponse({"status": "ok", "project": project})


@router.post("/{project_id}/archive")
async def archive_project(project_id: str):
    """Archive a project."""
    await get_db().initialize()
    await get_db().archive_project(project_id)
    return JSONResponse({"status": "ok"})


@router.post("/{project_id}/unarchive")
async def unarchive_project(project_id: str):
    """Restore an archived project."""
    await get_db().initialize()
    await get_db().unarchive_project(project_id)
    return JSONResponse({"status": "ok"})


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its directory."""
    await get_db().initialize()
    project = None
    projects = await get_db().get_projects(archived=False)
    for p in projects:
        if p["id"] == project_id:
            project = p
            break
    if not project:
        projects = await get_db().get_projects(archived=True)
        for p in projects:
            if p["id"] == project_id:
                project = p
                break
    if project:
        try:
            p = Path(project["path"])
            if p.exists() and p.is_relative_to(WORKSPACE_ROOT):
                import shutil
                shutil.rmtree(p)
        except Exception:
            pass
    await get_db().delete_project(project_id)
    return JSONResponse({"status": "ok"})


@router.get("/{project_id}/sessions")
async def list_sessions(project_id: str, archived: bool = False):
    """List sessions for a project."""
    await get_db().initialize()
    sessions = await get_db().get_sessions(project_id, archived=archived)
    return JSONResponse({"sessions": sessions})


@router.post("/{project_id}/sessions")
async def create_session(project_id: str, req: SessionCreate):
    """Create a new session for a project."""
    await get_db().initialize()
    session_id = str(uuid.uuid4())[:8]
    await get_db().create_session(session_id, project_id, req.name)
    await get_db().activate_session(session_id)
    return JSONResponse({"status": "ok", "id": session_id, "name": req.name})


@router.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str):
    """Set a session as active."""
    await get_db().initialize()
    await get_db().activate_session(session_id)
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: str):
    """Archive a session."""
    await get_db().initialize()
    await get_db().archive_session(session_id)
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/unarchive")
async def unarchive_session(session_id: str):
    """Restore an archived session."""
    await get_db().initialize()
    await get_db().unarchive_session(session_id)
    return JSONResponse({"status": "ok"})


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    await get_db().initialize()
    await get_db().delete_session(session_id)
    return JSONResponse({"status": "ok"})


@router.post("/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: SessionCreate):
    """Rename a session."""
    await get_db().initialize()
    await get_db().update_session(session_id, name=req.name)
    return JSONResponse({"status": "ok"})


@router.get("/info")
async def get_project_info():
    """Get current project information (backward compatibility)."""
    await get_db().initialize()
    active = await get_db().get_active_project()
    if not active:
        project_path = WORKSPACE_ROOT
        return JSONResponse({
            "name": "Emo AI",
            "path": str(project_path),
            "file_count": 0,
            "workspace": str(WORKSPACE_ROOT),
        })

    project_path = Path(active["path"])
    file_count = 0
    if project_path.exists():
        file_count = sum(1 for _ in project_path.rglob("*") if _.is_file())

    return JSONResponse({
        "id": active["id"],
        "name": active["name"],
        "path": active["path"],
        "description": active.get("description", ""),
        "file_count": file_count,
        "workspace": str(WORKSPACE_ROOT),
    })


@router.get("/files")
async def get_project_files(project_id: str = ""):
    """Get files in a project directory."""
    await get_db().initialize()

    project = None
    if project_id:
        projects = await get_db().get_projects(archived=False)
        for p in projects:
            if p["id"] == project_id:
                project = p
                break

    if not project:
        project = await get_db().get_active_project()

    if not project:
        return JSONResponse({"files": []})

    project_path = Path(project["path"])
    if not project_path.exists():
        return JSONResponse({"files": []})

    def get_files_recursive(path, base_path):
        items = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.'):
                    continue
                rel_path = str(item.relative_to(base_path))
                size = ""
                if item.is_file():
                    size_bytes = item.stat().st_size
                    if size_bytes > 1024:
                        size = f"{size_bytes/1024:.1f}KB"
                    elif size_bytes > 1024*1024:
                        size = f"{size_bytes/1024/1024:.1f}MB"
                    else:
                        size = f"{size_bytes}B"
                items.append({
                    "name": item.name,
                    "path": rel_path,
                    "is_directory": item.is_dir(),
                    "size": size,
                    "expanded": False,
                    "children": get_files_recursive(item, base_path) if item.is_dir() else []
                })
        except PermissionError:
            pass
        return items

    files = get_files_recursive(project_path, project_path)
    return JSONResponse({"files": files})


@router.get("/read-file")
async def read_file_content(project_id: str = "", file_path: str = ""):
    """Read content of a specific file."""
    from project_tools import WORKSPACE_ROOT, _safe_path
    await get_db().initialize()

    if not file_path:
        return JSONResponse({"content": "No file path provided"})

    project = None
    if project_id:
        projects = await get_db().get_projects(archived=False)
        for p in projects:
            if p["id"] == project_id:
                project = p
                break

    if not project:
        project = await get_db().get_active_project()

    if not project:
        return JSONResponse({"content": "No project selected"})

    try:
        file_full_path = _safe_path(Path(project["path"]) / file_path)
        
        if not file_full_path.exists():
            return JSONResponse({"content": "File not found"})
        
        # Handle Excel files - read as text for now
        ext = file_full_path.suffix.lower()
        if ext in ['.xlsx', '.xls', '.xlsm']:
            return JSONResponse({
                "content": f"This is an Excel file: {file_path}\n\nTo analyze Excel files properly, the AI should use Python to read and analyze this file with pandas.\n\nFile info:\n- Size: {file_full_path.stat().st_size / 1024:.1f} KB\n- Created: {file_full_path.stat().st_ctime}"
            })
        
        # Read text files
        content = file_full_path.read_text(encoding='utf-8', errors='replace')
        if len(content) > 10000:
            content = content[:10000] + "\n\n... (truncated)"
        
        return JSONResponse({"content": content})
    except Exception as e:
        return JSONResponse({"content": f"Error reading file: {str(e)}"})


@router.get("/browse-folders")
async def browse_folders(path: str = ""):
    """List sub-folders of a given path (server-side). Used by the new-project dialog."""
    from project_tools import WORKSPACE_ROOT

    base = WORKSPACE_ROOT
    if path:
        try:
            base = Path(path).expanduser().resolve()
        except Exception as e:
            return JSONResponse({"error": f"Invalid path: {e}", "folders": []})
    if not base.exists() or not base.is_dir():
        return JSONResponse({"error": "Path does not exist or is not a directory", "folders": []})

    parent = None
    if str(base) != "/":
        parent_path = base.parent
        if parent_path != base:
            parent = str(parent_path)

    folders = []
    try:
        for item in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if not item.is_dir():
                continue
            if item.name.startswith("."):
                continue
            try:
                folders.append({"name": item.name, "path": str(item)})
            except Exception:
                continue
    except PermissionError:
        return JSONResponse({"error": "Permission denied", "folders": [], "current": str(base), "parent": parent})

    return JSONResponse({"current": str(base), "parent": parent, "folders": folders[:200]})
