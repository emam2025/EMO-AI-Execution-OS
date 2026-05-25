#!/usr/bin/env python3
"""
Emo AI Orchestrator — Setup & Installation Script

Usage:
    python setup.py          # Full setup (venv + deps + .env)
    python setup.py --deps   # Install dependencies only
    python setup.py --check  # Check system requirements
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / "venv"
PYTHON = sys.executable


def print_header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_step(text: str) -> None:
    print(f"  [✓] {text}")


def print_error(text: str) -> None:
    print(f"  [✗] {text}")


def print_info(text: str) -> None:
    print(f"  [i] {text}")


def check_python_version() -> bool:
    """Check if Python version is 3.11+."""
    major, minor = sys.version_info[:2]
    if major == 3 and minor >= 11:
        print_step(f"Python {major}.{minor} ✓")
        return True
    print_error(f"Python {major}.{minor} — requires 3.11+")
    return False


def check_system_requirements() -> bool:
    """Check all system requirements."""
    print_header("Checking System Requirements")

    all_ok = True

    # Python version
    if not check_python_version():
        all_ok = False

    # pip
    try:
        subprocess.run(
            [PYTHON, "-m", "pip", "--version"],
            capture_output=True, check=True
        )
        print_step("pip is available")
    except subprocess.CalledProcessError:
        print_error("pip is not available")
        all_ok = False

    # git
    if shutil.which("git"):
        print_step("git is available")
    else:
        print_info("git is not installed (optional)")

    # Ollama (optional)
    if shutil.which("ollama"):
        print_step("Ollama is available (local LLM)")
    else:
        print_info("Ollama is not installed (optional — for local LLM)")

    return all_ok


def create_venv() -> bool:
    """Create a virtual environment."""
    print_header("Creating Virtual Environment")

    if VENV_DIR.exists():
        print_info(f"Virtual environment already exists at {VENV_DIR}")
        return True

    try:
        subprocess.run(
            [PYTHON, "-m", "venv", str(VENV_DIR)],
            check=True,
        )
        print_step(f"Virtual environment created at {VENV_DIR}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False


def install_dependencies() -> bool:
    """Install project dependencies."""
    print_header("Installing Dependencies")

    pip_path = VENV_DIR / "bin" / "pip"
    if not pip_path.exists():
        pip_path = Path(PYTHON).parent / "pip"

    try:
        subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip"],
            check=True,
        )
        print_step("pip upgraded")

        subprocess.run(
            [str(pip_path), "install", "-r", str(PROJECT_DIR / "requirements.txt")],
            check=True,
        )
        print_step("Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        return False


def create_env_file() -> bool:
    """Create .env file from .env.example."""
    print_header("Setting Up Environment")

    env_file = PROJECT_DIR / ".env"
    env_example = PROJECT_DIR / ".env.example"

    if env_file.exists():
        print_info(".env file already exists")
        return True

    if env_example.exists():
        shutil.copy(env_example, env_file)
        print_step(".env file created from .env.example")
        print_info("Please edit .env with your API keys")
        return True
    else:
        print_error(".env.example not found")
        return False


def create_log_dir() -> bool:
    """Create logs directory."""
    print_header("Setting Up Logs")

    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    print_step(f"Logs directory created at {log_dir}")
    return True


def run_tests() -> bool:
    """Run tests to verify installation."""
    print_header("Running Tests")

    pytest_path = VENV_DIR / "bin" / "pytest"
    if not pytest_path.exists():
        print_info("pytest not installed, skipping tests")
        return True

    try:
        result = subprocess.run(
            [str(pytest_path), "tests/", "-v", "--tb=short"],
            cwd=PROJECT_DIR,
            check=False,
        )
        if result.returncode == 0:
            print_step("All tests passed")
            return True
        else:
            print_info("Some tests failed or skipped (this is OK for initial setup)")
            return True
    except Exception as e:
        print_error(f"Failed to run tests: {e}")
        return False


def print_next_steps() -> None:
    """Print next steps for the user."""
    print_header("Setup Complete! Next Steps")

    print("  1. Edit .env with your API keys:")
    print(f"     nano {PROJECT_DIR}/.env")
    print()
    print("  2. (Optional) Install Ollama for local LLM:")
    print("     brew install ollama")
    print("     ollama pull llama3.2")
    print()
    print("  3. Start the server:")
    print("     source venv/bin/activate")
    print("     python main.py")
    print()
    print("  4. Open your browser:")
    print("     http://localhost:8080")
    print()


def main() -> int:
    """Main setup function."""
    print_header("Emo AI Orchestrator — Setup")

    args = sys.argv[1:]

    # --check: only check requirements
    if "--check" in args:
        return 0 if check_system_requirements() else 1

    # Check system requirements
    if not check_system_requirements():
        print_error("System requirements not met. Please fix the issues above.")
        return 1

    # --deps: only install dependencies
    if "--deps" in args:
        if not install_dependencies():
            return 1
        print_next_steps()
        return 0

    # Full setup
    steps = [
        ("Virtual Environment", create_venv),
        ("Dependencies", install_dependencies),
        ("Environment File", create_env_file),
        ("Logs Directory", create_log_dir),
        ("Tests", run_tests),
    ]

    for name, func in steps:
        if not func():
            print_error(f"Setup failed at: {name}")
            return 1

    print_next_steps()
    return 0


if __name__ == "__main__":
    sys.exit(main())
