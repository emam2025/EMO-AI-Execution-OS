"""E1 — FirecrackerSupport: MicroVM-based execution isolation.

Uses AWS Firecracker to spawn lightweight microVMs for
strong isolation between executions.

Prerequisites:
  - firecracker binary installed and in PATH
  - Kernel image (e.g., vmlinux.bin)
  - Root filesystem image (e.g., rootfs.ext4)

Usage:
    fc = FirecrackerRuntime(kernel="vmlinux.bin", rootfs="rootfs.ext4")
    result = fc.execute("python3 script.py", timeout=30)
    fc.cleanup(vm_id)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.sandbox.firecracker")


@dataclass
class FirecrackerResult:
    """Result of a Firecracker microVM execution."""
    vm_id: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str = ""


class FirecrackerRuntime:
    """MicroVM-based execution isolation using AWS Firecracker.

    Spawns ephemeral microVMs. Cleans up automatically.
    Designed as a pluggable backend for SandboxExecutor.
    """

    def __init__(
        self,
        kernel: str = "",
        rootfs: str = "",
        firecracker_binary: str = "firecracker",
        jailer_binary: str = "jailer",
        vsock_enabled: bool = False,
    ) -> None:
        self._kernel = kernel
        self._rootfs = rootfs
        self._fc_bin = firecracker_binary
        self._jailer_bin = jailer_binary
        self._vsock_enabled = vsock_enabled
        self._active_vms: Dict[str, Dict[str, Any]] = {}
        self._check_prerequisites()

    def _check_prerequisites(self) -> None:
        """Check if Firecracker prerequisites are met."""
        checks = {}

        # Check firecracker binary
        try:
            result = subprocess.run(
                [self._fc_bin, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            checks["firecracker"] = result.returncode == 0
        except FileNotFoundError:
            checks["firecracker"] = False
        except Exception:
            checks["firecracker"] = False

        # Check kernel image
        checks["kernel"] = self._kernel and os.path.exists(self._kernel)
        checks["rootfs"] = self._rootfs and os.path.exists(self._rootfs)

        if not checks.get("firecracker"):
            logger.warning("Firecracker binary '%s' not found", self._fc_bin)
        if not checks.get("kernel"):
            logger.warning("Kernel image not found: %s", self._kernel)
        if not checks.get("rootfs"):
            logger.warning("Rootfs image not found: %s", self._rootfs)

        self._prerequisites_met = all(checks.values())

    def is_available(self) -> bool:
        """Check if Firecracker is available on this system."""
        return self._prerequisites_met

    def execute(
        self,
        command: str,
        timeout: float = 30.0,
        cpu_limit: int = 1,
        memory_limit_mb: int = 256,
    ) -> FirecrackerResult:
        """Execute a command in an ephemeral microVM.

        Args:
            command: Shell command to run inside the VM.
            timeout: Max execution time in seconds.
            cpu_limit: Number of vCPUs.
            memory_limit_mb: Memory limit in MB.

        Returns:
            FirecrackerResult with VM output.
        """
        if not self.is_available():
            return FirecrackerResult(error="Firecracker prerequisites not met")

        vm_id = uuid.uuid4().hex[:12]
        api_socket = f"/tmp/firecracker-{vm_id}.sock"

        try:
            # Create temporary directory for VM
            vm_dir = tempfile.mkdtemp(prefix=f"fc_{vm_id}_")

            # Build and start Firecracker microVM
            fc_process = self._start_vm(vm_id, api_socket, vm_dir, cpu_limit, memory_limit_mb)
            if fc_process is None:
                return FirecrackerResult(vm_id=vm_id, error="Failed to start Firecracker VM")

            self._active_vms[vm_id] = {
                "process": fc_process,
                "socket": api_socket,
                "vm_dir": vm_dir,
                "started_at": time.time(),
                "timeout": timeout,
            }

            # Configure VM via API socket
            config_ok = self._configure_vm(api_socket, command)
            if not config_ok:
                self._cleanup_vm(vm_id)
                return FirecrackerResult(vm_id=vm_id, error="VM configuration failed")

            # Wait for VM to complete or timeout
            try:
                fc_process.wait(timeout=timeout)
                result = FirecrackerResult(
                    vm_id=vm_id,
                    exit_code=fc_process.returncode,
                )
            except subprocess.TimeoutExpired:
                fc_process.kill()
                result = FirecrackerResult(
                    vm_id=vm_id,
                    timed_out=True,
                    error=f"VM execution timed out after {timeout}s",
                )

            self._cleanup_vm(vm_id)
            return result

        except FileNotFoundError:
            return FirecrackerResult(error="Firecracker binary not found")
        except Exception as e:
            self._cleanup_vm(vm_id)
            return FirecrackerResult(vm_id=vm_id, error=str(e))

    def _start_vm(
        self,
        vm_id: str,
        api_socket: str,
        vm_dir: str,
        cpu_limit: int,
        memory_limit_mb: int,
    ) -> Optional[subprocess.Popen]:
        """Start a Firecracker microVM process."""
        try:
            if os.path.exists(api_socket):
                os.unlink(api_socket)

            proc = subprocess.Popen(
                [self._fc_bin,
                 "--api-sock", api_socket,
                 "--id", vm_id,
                 "--seccomp-level", "2"],
                cwd=vm_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for API socket to be ready
            for _ in range(50):
                if os.path.exists(api_socket):
                    return proc
                time.sleep(0.1)

            proc.kill()
            return None

        except Exception:
            return None

    def _configure_vm(self, api_socket: str, command: str) -> bool:
        """Configure a running Firecracker VM via its API.

        Sends configuration via the Firecracker API socket.
        """
        import http.client
        import urllib.parse

        try:
            conn = http.client.HTTPConnection(
                "localhost",
                timeout=5,
                source_address=("unix", api_socket),
            )

            # 1. Set kernel image
            body = json.dumps({
                "kernel_image_path": self._kernel,
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
            })
            conn.request("PUT", "/boot-source", body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status not in (200, 204):
                conn.close()
                return False

            # 2. Set rootfs
            body = json.dumps({
                "drive_id": "rootfs",
                "path_on_host": self._rootfs,
                "is_root_device": True,
                "is_read_only": False,
            })
            conn.request("PUT", "/drives/rootfs", body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status not in (200, 204):
                conn.close()
                return False

            # 3. Set the vsock or serial for command output
            if self._vsock_enabled:
                body = json.dumps({"vsock_id": "vsock0", "guest_cid": 3, "uds_path": "/tmp/vsock.sock"})
                conn.request("PUT", "/vsock", body, {"Content-Type": "application/json"})
                resp = conn.getresponse()

            # 4. Start the VM
            conn.request("PUT", "/actions", json.dumps({"action_type": "InstanceStart"}), {"Content-Type": "application/json"})
            resp = conn.getresponse()
            conn.close()
            return resp.status in (200, 204)

        except Exception:
            return False

    def _cleanup_vm(self, vm_id: str) -> None:
        """Clean up a microVM."""
        info = self._active_vms.pop(vm_id, None)
        if info is None:
            return

        # Kill process
        proc = info.get("process")
        if proc and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        # Clean up socket
        sock = info.get("socket")
        if sock and os.path.exists(sock):
            try:
                os.unlink(sock)
            except OSError:
                pass

        # Clean up temp dir
        vm_dir = info.get("vm_dir")
        if vm_dir and os.path.exists(vm_dir):
            try:
                shutil.rmtree(vm_dir, ignore_errors=True)
            except Exception:
                pass

    def cleanup_all(self) -> int:
        """Clean up all tracked VMs."""
        count = 0
        for vm_id in list(self._active_vms.keys()):
            self._cleanup_vm(vm_id)
            count += 1
        return count

    def list_active(self) -> Dict[str, Dict[str, Any]]:
        """List all tracked active VMs."""
        return {
            vm_id: {k: v for k, v in info.items() if k != "process"}
            for vm_id, info in self._active_vms.items()
        }
