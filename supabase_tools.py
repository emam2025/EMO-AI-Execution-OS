import os
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from tools import Tool


SUPABASE_API = "https://api.supabase.com"
SUPABASE_MANAGEMENT_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


class SupabaseCreateProject(Tool):
    name = "supabase_create_project"
    description = "Create a new Supabase project via API (requires SUPABASE_SERVICE_KEY)"
    category = "Supabase"
    icon = "🗄️"
    parameters = {"name": "string", "organization_id": "string", "plan": "string", "region": "string", "db_password": "string"}

    def run(self, name="", organization_id="", plan="free", region="us-east-1", db_password=""):
        if not SUPABASE_MANAGEMENT_KEY:
            return "Error: SUPABASE_SERVICE_KEY not configured in environment"
        if not name:
            return "Error: name is required"
        data = {
            "name": name,
            "organization_id": organization_id,
            "plan": plan,
            "region": region,
        }
        if db_password:
            data["db_pass"] = db_password
        req = Request(
            f"{SUPABASE_API}/v1/projects",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {SUPABASE_MANAGEMENT_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=60) as r:
                result = json.loads(r.read().decode())
            return f"Project created: {result.get('name', name)}\nID: {result.get('id', '')}\nURL: {result.get('url', '')}"
        except Exception as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            return f"Supabase project creation failed: {body[:500]}"


class SupabaseCreateTable(Tool):
    name = "supabase_create_table"
    description = "Create a table in Supabase via SQL or REST"
    category = "Supabase"
    icon = "📊"
    parameters = {"table_name": "string", "schema_sql": "string", "supabase_url": "string", "service_role_key": "string"}

    def run(self, table_name="", schema_sql="", supabase_url="", service_role_key=""):
        if not all([table_name, schema_sql]):
            return "Error: table_name and schema_sql are required"
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        if not url or not key:
            return "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured"
        sql_endpoint = f"{url}/rest/v1/rpc/pg_exec"
        data = json.dumps({"query": schema_sql}).encode()
        req = Request(sql_endpoint, data=data, headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        }, method="POST")
        # Try direct SQL API; if unavailable, use management API
        req2 = Request(
            f"{SUPABASE_API}/v1/projects/{url.split('//')[1].split('.')[0]}/sql",
            data=json.dumps({"query": schema_sql}).encode(),
            headers={
                "Authorization": f"Bearer {os.environ.get('SUPABASE_SERVICE_KEY', '')}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req2, timeout=30) as r:
                result = r.read().decode()
            return f"Table '{table_name}' created via management API"
        except Exception:
            pass
        return f"[SupabaseCreateTable] Would execute SQL for table '{table_name}'. Schema: {schema_sql[:200]}...\nTip: Use supabase CLI or SQL editor in dashboard to run this."


class SupabaseInsertData(Tool):
    name = "supabase_insert_data"
    description = "Insert data into a Supabase table via REST API"
    category = "Supabase"
    icon = "➕"
    parameters = {"table_name": "string", "data": "string", "supabase_url": "string", "service_role_key": "string"}

    def run(self, table_name="", data="{}", supabase_url="", service_role_key=""):
        if not table_name:
            return "Error: table_name is required"
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        if not url or not key:
            return "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured"
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            return "Error: data must be valid JSON"
        endpoint = f"{url}/rest/v1/{table_name}"
        req = Request(endpoint, data=json.dumps(parsed).encode(), headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }, method="POST")
        try:
            with urlopen(req, timeout=30) as r:
                result = json.loads(r.read().decode())
            return json.dumps(result, indent=2, ensure_ascii=False)[:3000]
        except Exception as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            return f"Insert failed: {body[:500]}"


class SupabaseQuery(Tool):
    name = "supabase_query"
    description = "Execute SQL query or REST filter on Supabase table"
    category = "Supabase"
    icon = "🔍"
    parameters = {"table_name": "string", "query_type": "string", "filters": "string", "sql": "string", "supabase_url": "string", "service_role_key": "string"}

    def run(self, table_name="", query_type="select", filters="", sql="", supabase_url="", service_role_key=""):
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        if sql:
            cmd = ["supabase", "db", "query", sql]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return (result.stdout or result.stderr)[:3000] if result.returncode == 0 else f"SQL error: {result.stderr[:500]}"
            except FileNotFoundError:
                pass
        if not all([url, key, table_name]):
            return "Error: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and table_name required for REST query"
        endpoint = f"{url}/rest/v1/{table_name}"
        params = f"?select=*"
        if filters:
            try:
                fdata = json.loads(filters) if isinstance(filters, str) else filters
                for k, v in fdata.items():
                    params += f"&{k}=eq.{v}"
            except Exception:
                params += f"&{filters}"
        req = Request(endpoint + params, headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
        }, method="GET")
        try:
            with urlopen(req, timeout=30) as r:
                result = json.loads(r.read().decode())
            items = result if isinstance(result, list) else [result]
            return json.dumps(items[:20], indent=2, ensure_ascii=False) + (f"\n... ({len(items)} total)" if len(items) > 20 else "") if items else "No results"
        except Exception as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            return f"Query failed: {body[:500]}"


class SupabaseAuthSetup(Tool):
    name = "supabase_auth_setup"
    description = "Generate Supabase Auth configuration file"
    category = "Supabase"
    icon = "🔐"
    parameters = {"project_dir": "string", "providers": "string", "supabase_url": "string", "anon_key": "string"}

    def run(self, project_dir=".", providers="email", supabase_url="", anon_key=""):
        target = Path(project_dir).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        key = anon_key or os.environ.get("SUPABASE_ANON_KEY", "")
        provider_list = [p.strip() for p in providers.split(",")]
        auth_config = {
            "supabaseUrl": url,
            "supabaseAnonKey": key,
            "enabledProviders": provider_list,
        }
        (target / "supabase-auth-config.json").write_text(json.dumps(auth_config, indent=2))
        return f"Supabase auth config written for providers: {', '.join(provider_list)}"


class SupabaseStorageUpload(Tool):
    name = "supabase_storage_upload"
    description = "Upload a file to Supabase Storage"
    category = "Supabase"
    icon = "☁️"
    parameters = {"bucket": "string", "file_path": "string", "destination_path": "string", "supabase_url": "string", "service_role_key": "string"}

    def run(self, bucket="", file_path="", destination_path="", supabase_url="", service_role_key=""):
        if not all([bucket, file_path]):
            return "Error: bucket and file_path are required"
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        url = supabase_url or os.environ.get("SUPABASE_URL", "")
        if not url or not key:
            return "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured"
        fp = Path(file_path).expanduser()
        if not fp.exists():
            return f"File not found: {fp}"
        dest = destination_path or fp.name
        endpoint = f"{url}/storage/v1/object/{bucket}/{dest}"
        data = fp.read_bytes()
        req = Request(endpoint, data=data, headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/octet-stream",
        }, method="POST")
        try:
            with urlopen(req, timeout=120) as r:
                result = r.read().decode()
            return f"Uploaded {fp.name} to {bucket}/{dest}\n{result}"
        except Exception as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            return f"Upload failed: {body[:500]}"
