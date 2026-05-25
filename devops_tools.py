import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from tools import Tool


class VercelDeploy(Tool):
    name = "vercel_deploy"
    description = "Deploy project to Vercel (requires Vercel CLI)"
    category = "DevOps"
    icon = "▲"
    parameters = {"project_dir": "string", "prod": "boolean"}

    def run(self, project_dir: str = ".", prod: bool = False) -> str:
        """
        Deploy a project to Vercel.
        Args:
            project_dir: Path to project directory
            prod: Deploy to production (otherwise preview)
        """
        target = Path(project_dir).expanduser().resolve()
        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        cmd = ["vercel", "--cwd", str(target)]
        if prod:
            cmd.append("--prod")
        cmd.append("--yes")  # Skip prompts

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if result.returncode != 0:
                return f"❌ Vercel deploy failed:\n{result.stderr[:800]}"
            output = result.stdout[:1500] or "✅ Deployed to Vercel"
            return output
        except FileNotFoundError:
            return "❌ Vercel CLI not installed. Install with: npm install -g vercel"
        except subprocess.TimeoutExpired:
            return "❌ Deployment timed out (3 minutes)"
        except Exception as e:
            return f"❌ Deploy error: {e}"


class DockerBuild(Tool):
    name = "docker_build"
    description = "Build a Docker image from a Dockerfile"
    category = "DevOps"
    icon = "🐳"
    parameters = {"project_dir": "string", "image_name": "string", "tag": "string"}

    def run(self, project_dir: str = ".", image_name: str = "emo-app", tag: str = "latest") -> str:
        """
        Build a Docker image.
        Args:
            project_dir: Directory containing Dockerfile
            image_name: Name for the image
            tag: Tag for the image
        """
        target = Path(project_dir).expanduser().resolve()
        dockerfile = target / "Dockerfile"
        if not dockerfile.exists():
            return f"❌ No Dockerfile found in {target}"

        full_tag = f"{image_name}:{tag}"
        try:
            result = subprocess.run(
                ["docker", "build", "-t", full_tag, str(target)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode != 0:
                return f"❌ Docker build failed:\n{result.stderr[:800]}"
            # Extract only last few lines of build output
            lines = result.stdout.splitlines()
            summary = "\n".join(lines[-20:]) if len(lines) > 20 else result.stdout
            return f"✅ Image built: {full_tag}\n{summary}"
        except FileNotFoundError:
            return "❌ Docker not installed or not in PATH"
        except subprocess.TimeoutExpired:
            return "❌ Build timed out (5 minutes)"
        except Exception as e:
            return f"❌ Docker build error: {e}"


class DockerRun(Tool):
    name = "docker_run"
    description = "Run a Docker container from an image"
    category = "DevOps"
    icon = "▶️"
    parameters = {
        "image_name": "string",
        "tag": "string",
        "port_mapping": "string",
        "detach": "boolean",
        "name": "string",
        "env_file": "string",
    }

    def run(
        self,
        image_name: str = "emo-app",
        tag: str = "latest",
        port_mapping: str = "8000:8000",
        detach: bool = True,
        name: str = "",
        env_file: str = "",
    ) -> str:
        """
        Run a Docker container.
        Args:
            image_name: Image name
            tag: Image tag
            port_mapping: Host:Container port mapping (e.g., "8000:8000")
            detach: Run in background
            name: Container name (optional)
            env_file: Path to .env file for environment variables
        """
        full_image = f"{image_name}:{tag}"
        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        if port_mapping:
            cmd.extend(["-p", port_mapping])
        if name:
            cmd.extend(["--name", name])
        if env_file:
            env_path = Path(env_file).expanduser().resolve()
            if env_path.is_file():
                cmd.extend(["--env-file", str(env_path)])
            else:
                return f"❌ Environment file not found: {env_file}"
        cmd.append(full_image)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )
            if result.returncode != 0:
                return f"❌ Docker run failed:\n{result.stderr[:800]}"
            container_id = result.stdout.strip()[:12]
            return (
                f"✅ Container started: {container_id}\n"
                f"   Port mapping: {port_mapping}\n"
                f"   View logs: docker logs {container_id}\n"
                f"   Stop: docker stop {container_id}"
            )
        except FileNotFoundError:
            return "❌ Docker not installed or not in PATH"
        except subprocess.TimeoutExpired:
            return "❌ Run command timed out"
        except Exception as e:
            return f"❌ Docker run error: {e}"


class EnvManager(Tool):
    name = "env_manager"
    description = "Manage environment variables (view, set, load from .env)"
    category = "DevOps"
    icon = "🔧"
    parameters = {
        "action": "string",
        "project_dir": "string",
        "key": "string",
        "value": "string",
    }

    def _parse_env_file(self, path: Path) -> Dict[str, str]:
        """Parse a .env file into a dictionary, handling comments and empty lines."""
        env_dict = {}
        if not path.exists():
            return env_dict
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                # Split only on first '='
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                env_dict[k] = v
        return env_dict

    def _write_env_file(self, path: Path, env_dict: Dict[str, str]) -> None:
        """Write dictionary to .env file."""
        lines = []
        # Preserve original comments? Not implemented for simplicity.
        for k, v in sorted(env_dict.items()):
            lines.append(f"{k}={v}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self, action: str = "list", project_dir: str = ".", key: str = "", value: str = "") -> str:
        """
        Manage .env file and environment variables.
        Actions: list, get, set, unset, load, init
        """
        target = Path(project_dir).expanduser().resolve()
        env_file = target / ".env"
        action = action.lower().strip()

        # Load current environment file into dict
        current = self._parse_env_file(env_file)

        if action in ("list", "view"):
            if not env_file.exists():
                return f"📄 No .env file found in {target}\nYou can create one with action='init'"
            if not current:
                return f"📄 {env_file} exists but is empty."
            output = "\n".join(f"{k}={v}" for k, v in current.items())
            return f"📄 {env_file} contents:\n{output}"

        elif action == "get":
            if not key:
                return "❌ Missing 'key' parameter for get action"
            # Check environment first (runtime override)
            env_value = os.environ.get(key, "")
            if env_value:
                return f"{key}={env_value} (runtime)"
            # Fall back to file
            value = current.get(key, "")
            if value:
                return f"{key}={value} (from .env)"
            return f"❌ {key} not set"

        elif action == "set":
            if not key:
                return "❌ Missing 'key' parameter for set action"
            if value == "":
                return "❌ Missing 'value' parameter for set action"
            # Update dictionary
            current[key] = value
            self._write_env_file(env_file, current)
            # Also set in current process environment
            os.environ[key] = value
            return f"✅ Set {key}={value} in {env_file}"

        elif action == "unset":
            if not key:
                return "❌ Missing 'key' parameter for unset action"
            if key in current:
                del current[key]
                self._write_env_file(env_file, current)
            if key in os.environ:
                del os.environ[key]
            return f"✅ Removed {key} from environment"

        elif action == "load":
            if not env_file.exists():
                return f"❌ {env_file} does not exist. Create it with action='init'"
            # Load into os.environ
            for k, v in current.items():
                os.environ[k] = v
            return f"✅ Loaded {len(current)} variables from {env_file} into runtime environment"

        elif action == "init":
            if env_file.exists():
                return f"⚠️ {env_file} already exists. Not overwritten."
            self._write_env_file(env_file, {})
            return f"✅ Created empty {env_file}. Edit to add variables like:\nKEY=value"

        else:
            return f"❌ Unknown action: {action}. Supported: list, get, set, unset, load, init"