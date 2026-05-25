import os
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from tools import Tool


def _get_config():
    return {
        "api_key": os.environ.get("FIREBASE_API_KEY", ""),
        "project_id": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "service_account": os.environ.get("FIREBASE_SERVICE_ACCOUNT", ""),
    }


class FirebaseInitProject(Tool):
    name = "firebase_init_project"
    description = "Initialize Firebase project configuration in a local directory"
    category = "Firebase"
    icon = "🔥"
    parameters = {"project_dir": "string", "project_id": "string"}

    def run(self, project_dir=".", project_id=""):
        target = Path(project_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        config = {
            "projectId": project_id or _get_config()["project_id"],
            "databaseURL": f"https://{project_id or _get_config()['project_id']}.firebaseio.com" if (project_id or _get_config()["project_id"]) else "",
            "storageBucket": f"{project_id or _get_config()['project_id']}.appspot.com" if (project_id or _get_config()["project_id"]) else "",
        }
        firebase_json = target / "firebase.json"
        firebase_json.write_text(json.dumps(config, indent=2))
        dot_env = target / ".firebaserc"
        dot_env.write_text(json.dumps({"projects": {"default": project_id or _get_config()["project_id"] or ""}}, indent=2))
        (target / "public").mkdir(exist_ok=True)
        index = target / "public" / "index.html"
        if not index.exists():
            index.write_text("<!DOCTYPE html><html><head><title>Firebase App</title></head><body><h1>Firebase App</h1></body></html>")
        return f"Firebase project initialized at {target}"


class FirebaseAuthSetup(Tool):
    name = "firebase_auth_setup"
    description = "Generate Firebase Authentication configuration for email/password and social providers"
    category = "Firebase"
    icon = "🔐"
    parameters = {"project_dir": "string", "providers": "string"}

    def run(self, project_dir=".", providers="email"):
        target = Path(project_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        config = _get_config()
        provider_list = [p.strip().lower() for p in providers.split(",")]
        auth_config = {
            "apiKey": config["api_key"],
            "authDomain": f"{config['project_id']}.firebaseapp.com" if config["project_id"] else "",
            "enabledProviders": provider_list,
        }
        auth_file = target / "firebase-auth-config.json"
        auth_file.write_text(json.dumps(auth_config, indent=2))
        return f"Auth config written for providers: {', '.join(provider_list)}"


class FirebaseFirestoreWrite(Tool):
    name = "firebase_firestore_write"
    description = "Write data to Firestore via REST API"
    category = "Firebase"
    icon = "📝"
    parameters = {"collection": "string", "document_id": "string", "data": "string"}

    def run(self, collection="", document_id="", data="{}"):
        if not collection:
            return "Error: collection is required"
        config = _get_config()
        if not config["project_id"]:
            return "Error: FIREBASE_PROJECT_ID not configured"
        project_id = config["project_id"]
        api_key = config["api_key"]
        try:
            parsed_data = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            return "Error: data must be valid JSON"
        fields = {}
        for key, val in parsed_data.items():
            if isinstance(val, str):
                fields[key] = {"stringValue": val}
            elif isinstance(val, (int, float)):
                fields[key] = {"doubleValue": val}
            elif isinstance(val, bool):
                fields[key] = {"booleanValue": val}
            elif isinstance(val, list):
                fields[key] = {"arrayValue": {"values": [{"stringValue": str(v)} for v in val]}}
            else:
                fields[key] = {"stringValue": str(val)}
        body = {"fields": fields}
        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection}"
        if document_id:
            url += f"/{document_id}?key={api_key}"
            result = _gh_patch(url, body)
        else:
            url += f"?key={api_key}"
            result = _gh_post(url, body)
        if "error" in result:
            return f"Firestore write failed: {result['error'].get('message', str(result))}"
        return f"Data written to {collection}/{document_id or result.get('name', '')}"


class FirebaseFirestoreRead(Tool):
    name = "firebase_firestore_read"
    description = "Read data from Firestore via REST API"
    category = "Firebase"
    icon = "👁️"
    parameters = {"collection": "string", "document_id": "string"}

    def run(self, collection="", document_id=""):
        if not collection:
            return "Error: collection is required"
        config = _get_config()
        if not config["project_id"]:
            return "Error: FIREBASE_PROJECT_ID not configured"
        api_key = config["api_key"]
        url = f"https://firestore.googleapis.com/v1/projects/{config['project_id']}/databases/(default)/documents/{collection}"
        if document_id:
            url += f"/{document_id}"
        url += f"?key={api_key}"
        result = _gh_get(url)
        if "error" in result:
            return f"Firestore read failed: {result['error'].get('message', str(result))}"
        if document_id:
            doc = result.get("fields", {})
            return json.dumps({k: list(v.values())[0] if isinstance(v, dict) else v for k, v in doc.items()}, indent=2)
        docs = result.get("documents", [])
        return json.dumps([{"id": d.get("name", ""), "fields": d.get("fields", {})} for d in docs], indent=2, ensure_ascii=False)


class FirebaseDeploy(Tool):
    name = "firebase_deploy"
    description = "Deploy project to Firebase Hosting"
    category = "Firebase"
    icon = "🚀"
    parameters = {"project_dir": "string"}

    def run(self, project_dir="."):
        target = Path(project_dir).expanduser().resolve()
        if not (target / "firebase.json").exists():
            return f"No firebase.json found in {target}. Run firebase_init_project first."
        try:
            result = subprocess.run(["firebase", "deploy", "--project", _get_config()["project_id"]],
                                    cwd=str(target), capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return f"Deploy failed: {result.stderr[:500]}"
            return result.stdout[:1000] or "Deployed successfully"
        except FileNotFoundError:
            return "Firebase CLI not installed. Install with: npm install -g firebase-tools"
        except Exception as e:
            return f"Deploy error: {e}"


def _gh_post(url, data):
    req = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        try:
            return json.loads(body)
        except Exception:
            return {"error": {"message": str(e)[:300]}}


def _gh_patch(url, data):
    req = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method="PATCH")
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        try:
            return json.loads(body)
        except Exception:
            return {"error": {"message": str(e)[:300]}}


def _gh_get(url):
    try:
        with urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        try:
            return json.loads(body)
        except Exception:
            return {"error": {"message": str(e)[:300]}}
