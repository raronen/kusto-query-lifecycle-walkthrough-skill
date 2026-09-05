from __future__ import annotations

import argparse
import ctypes
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ctypes import wintypes

from plan_recovery import build_queryplan_command

if sys.platform == "win32":
    import _winapi


class LocalTraceDriverError(RuntimeError):
    pass


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class WindowsJob:
    _KILL_ON_CLOSE = 0x00002000

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise LocalTraceDriverError("The local trace driver requires Windows Job Objects.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process: subprocess.Popen[Any]) -> None:
        if not self._kernel32.AssignProcessToJobObject(
            self._handle, wintypes.HANDLE(int(process._handle))
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_processes(self) -> int:
        info = _BasicAccountingInformation()
        if not self._kernel32.QueryInformationJobObject(
            self._handle, 1, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(info.ActiveProcesses)

    def terminate_and_wait(self, timeout: float) -> bool:
        if self.active_processes() and not self._kernel32.TerminateJobObject(
            self._handle, 1
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.active_processes() == 0:
                return True
            time.sleep(0.05)
        return self.active_processes() == 0

    def close(self) -> None:
        if getattr(self, "_handle", None):
            if not self._kernel32.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None


def _safe_windows_command(
    command: list[str], cwd: Path
) -> tuple[list[str], str]:
    candidate = Path(command[0])
    local_candidate = (cwd / candidate).resolve()
    executable = (
        str(local_candidate)
        if not candidate.is_absolute() and local_candidate.is_file()
        else shutil.which(command[0]) or command[0]
    )
    if Path(executable).suffix.lower() not in {".cmd", ".bat"}:
        return command, subprocess.list2cmdline(command)
    comspec = os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")
    batch_command_line = subprocess.list2cmdline([executable, *command[1:]])
    wrapped = [
        comspec,
        "/d",
        "/s",
        "/c",
        batch_command_line,
    ]
    command_line = (
        subprocess.list2cmdline([comspec, "/d", "/s", "/c"])
        + f' "{batch_command_line}"'
    )
    return wrapped, command_line


class SuspendedProcess:
    _CREATE_SUSPENDED = 0x00000004
    _CREATE_UNICODE_ENVIRONMENT = 0x00000400
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 258
    _INFINITE = 0xFFFFFFFF
    _STILL_ACTIVE = 259

    def __init__(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise LocalTraceDriverError("Suspended launch requires Windows.")
        self.command, command_line = _safe_windows_command(command, cwd)
        startup = subprocess.STARTUPINFO()
        process_handle, thread_handle, pid, _ = _winapi.CreateProcess(
            None,
            command_line,
            None,
            None,
            False,
            self._CREATE_SUSPENDED | self._CREATE_UNICODE_ENVIRONMENT,
            env,
            str(cwd),
            startup,
        )
        self._handle = process_handle
        self._thread_handle = thread_handle
        self.pid = int(pid)
        self._resumed = False

    def resume(self) -> None:
        if self._resumed:
            raise LocalTraceDriverError("Suspended process was already resumed.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        result = kernel32.ResumeThread(wintypes.HANDLE(self._thread_handle))
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        _winapi.CloseHandle(self._thread_handle)
        self._thread_handle = None
        self._resumed = True

    def wait(self, timeout: float | None = None) -> int:
        milliseconds = (
            self._INFINITE
            if timeout is None
            else max(0, min(int(timeout * 1000), self._INFINITE - 1))
        )
        result = _winapi.WaitForSingleObject(self._handle, milliseconds)
        if result == self._WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(self.command, timeout)
        if result != self._WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(_winapi.GetExitCodeProcess(self._handle))

    def poll(self) -> int | None:
        result = _winapi.WaitForSingleObject(self._handle, 0)
        if result == self._WAIT_TIMEOUT:
            return None
        if result != self._WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = int(_winapi.GetExitCodeProcess(self._handle))
        return None if code == self._STILL_ACTIVE else code

    def close(self) -> None:
        if self._thread_handle is not None:
            _winapi.CloseHandle(self._thread_handle)
            self._thread_handle = None
        if self._handle is not None:
            _winapi.CloseHandle(self._handle)
            self._handle = None


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _loopback_endpoint(value: str, location: str) -> tuple[str, int]:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise LocalTraceDriverError(f"{location} must be an absolute HTTP(S) URI.")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname.lower() != "localhost":
            raise LocalTraceDriverError(f"{location} must use a loopback host.")
    else:
        if not address.is_loopback:
            raise LocalTraceDriverError(f"{location} must use a loopback address.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise LocalTraceDriverError(f"{location} has an invalid port.") from exc
    if port is None:
        raise LocalTraceDriverError(f"{location} must use an explicit non-default port.")
    return parsed.hostname.lower(), port


def _outside(path: Path, parent: Path, location: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return
    raise LocalTraceDriverError(f"{location} must be outside '{parent}'.")


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        raise LocalTraceDriverError("PowerShell is required for process/port ownership checks.")
    return executable


def _powershell_json(script: str, *arguments: str) -> Any:
    environment = os.environ.copy()
    environment["KUSTO_TRACE_DRIVER_ARGS"] = json.dumps(arguments)
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$inputArgs=@(ConvertFrom-Json $env:KUSTO_TRACE_DRIVER_ARGS);" + script,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return json.loads(result.stdout) if result.stdout.strip() else []


def _listener_pids(port: int) -> list[int]:
    value = _powershell_json(
        (
            "$items=@(Get-NetTCPConnection -State Listen -LocalPort ([int]$inputArgs[0]) "
            "-ErrorAction Ignore | Select-Object -ExpandProperty OwningProcess "
            "-Unique); ConvertTo-Json -Compress -InputObject $items"
        ),
        str(port),
    )
    if isinstance(value, int):
        return [value]
    return sorted(int(item) for item in value)


def _descendant_pids(root_pid: int) -> list[int]:
    rows = _powershell_json(
        (
            "$items=@(Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId); "
            "ConvertTo-Json -Compress -InputObject $items"
        )
    )
    if isinstance(rows, dict):
        rows = [rows]
    children: dict[int, list[int]] = {}
    for row in rows:
        children.setdefault(int(row["ParentProcessId"]), []).append(int(row["ProcessId"]))
    result: list[int] = []
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, []):
            if child not in result:
                result.append(child)
                pending.append(child)
    return result


def _stop_exact_pids(pids: list[int]) -> None:
    if not pids:
        return
    _powershell_json(
        (
            "$ids=@($inputArgs | ForEach-Object {[int]$_}); "
            "foreach($id in $ids){if(Get-Process -Id $id -ErrorAction Ignore){"
            "Stop-Process -Id $id -Force -ErrorAction Stop}}; "
            "@() | ConvertTo-Json -Compress"
        ),
        *(str(pid) for pid in pids),
    )


def _existing_pids(pids: list[int]) -> list[int]:
    if not pids:
        return []
    value = _powershell_json(
        (
            "$ids=@($inputArgs | ForEach-Object {[int]$_}); "
            "$items=@(foreach($id in $ids){if(Get-Process -Id $id "
            "-ErrorAction Ignore){$id}}); "
            "ConvertTo-Json -Compress -InputObject $items"
        ),
        *(str(pid) for pid in pids),
    )
    if isinstance(value, int):
        return [value]
    return sorted(int(item) for item in value)


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _worktree_registered(primary: Path, worktree: Path) -> bool:
    listing = _git(primary, "worktree", "list", "--porcelain")
    expected = os.path.normcase(str(worktree.resolve()))
    return any(
        line.startswith("worktree ")
        and os.path.normcase(str(Path(line.removeprefix("worktree ")).resolve()))
        == expected
        for line in listing.splitlines()
    )


def _create_owned_worktree_root(root: Path) -> tuple[Path, str, str]:
    root.mkdir(parents=False, exist_ok=False)
    token = secrets.token_hex(32)
    marker = root / ".kusto-local-trace-owner.json"
    marker_content = json.dumps(
        {"driver": "local_trace_driver.v1", "token": token},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(marker_content)
    return marker, token, hashlib.sha256(marker_content.encode("utf-8")).hexdigest()


def _owned_root_marker_matches(root: Path, marker: Path, token: str) -> bool:
    if not root.is_dir() or root.is_symlink() or not marker.is_file() or marker.is_symlink():
        return False
    expected = json.dumps(
        {"driver": "local_trace_driver.v1", "token": token},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        return marker.read_text(encoding="utf-8") == expected
    except OSError:
        return False


def _command(value: str, location: str) -> list[str]:
    try:
        command = json.loads(value)
    except json.JSONDecodeError as exc:
        raise LocalTraceDriverError(f"{location} must be a JSON argv array.") from exc
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise LocalTraceDriverError(f"{location} must be a nonempty JSON string array.")
    return command


def _reject_primary_references(
    command: list[str], primary: Path, location: str
) -> None:
    primary_text = os.path.normcase(str(primary.resolve()))
    for index, argument in enumerate(command):
        if primary_text in os.path.normcase(argument):
            raise LocalTraceDriverError(
                f"{location}[{index}] must not reference the primary checkout."
            )


def run_local_trace(args: argparse.Namespace) -> dict[str, Any]:
    primary = Path(args.primary_checkout).resolve()
    worktree_root = Path(args.worktree).resolve()
    worktree = worktree_root / "checkout"
    ownership_marker = worktree_root / ".kusto-local-trace-owner.json"
    patch = Path(args.instrumentation_patch).resolve()
    trace_output = Path(args.trace_output).resolve()
    receipt_file = Path(args.receipt_file).resolve()
    query_path = Path(args.query_file).resolve()
    if not (primary / ".git").exists():
        raise LocalTraceDriverError("primary checkout must be a git repository.")
    if worktree_root.exists():
        raise LocalTraceDriverError("Disposable worktree root must not already exist.")
    _outside(worktree_root, primary, "Disposable worktree root")
    _outside(primary, worktree_root, "Primary checkout")
    _outside(trace_output, primary, "Trace output")
    _outside(receipt_file, primary, "Receipt file")
    _outside(trace_output, worktree_root, "Trace output")
    _outside(receipt_file, worktree_root, "Receipt file")
    if not patch.is_file():
        raise LocalTraceDriverError("Instrumentation patch does not exist.")
    cluster_host, cluster_port = _loopback_endpoint(args.cluster_uri, "cluster URI")
    trace_host, trace_port = _loopback_endpoint(args.trace_url, "trace URL")
    if (cluster_host, cluster_port) != (trace_host, trace_port):
        raise LocalTraceDriverError(
            "Trace URL must use the same isolated loopback endpoint and port as cluster URI."
        )
    preexisting_listener_pids = _listener_pids(cluster_port)
    if preexisting_listener_pids:
        raise LocalTraceDriverError(
            "Requested loopback port is already owned; refusing to stop or replace an existing Engine."
        )
    query = query_path.read_text(encoding="utf-8")
    command = build_queryplan_command(query)
    build_command = _command(args.build_command_json, "--build-command-json")
    service_command = _command(args.service_command_json, "--service-command-json")
    _reject_primary_references(
        build_command, primary, "--build-command-json"
    )
    _reject_primary_references(
        service_command, primary, "--service-command-json"
    )
    request_scope = args.request_scope
    if not isinstance(request_scope, str) or not request_scope.strip():
        raise LocalTraceDriverError("A deterministic nonempty request scope is required.")
    primary_head_before = _git(primary, "rev-parse", "HEAD")
    resolved_base_ref = _git(
        primary, "rev-parse", f"{args.base_ref}^{{commit}}"
    )
    if resolved_base_ref != primary_head_before:
        raise LocalTraceDriverError(
            "--base-ref must resolve exactly to the primary checkout HEAD."
        )
    primary_status_before = _git(
        primary, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if primary_status_before:
        raise LocalTraceDriverError(
            "Primary checkout must be clean, including tracked and untracked files."
        )
    primary_head_tree = _git(primary, "rev-parse", "HEAD^{tree}")
    primary_index_tree_before = _git(primary, "write-tree")
    if primary_index_tree_before != primary_head_tree:
        raise LocalTraceDriverError("Primary checkout index does not match HEAD.")
    receipt: dict[str, Any] = {
        "driver": "local_trace_driver.v1",
        "primary_checkout": str(primary),
        "worktree_path": str(worktree),
        "worktree_root": str(worktree_root),
        "worktree_isolated": True,
        "ownership_marker_digest_sha256": "",
        "ownership_marker_validated": False,
        "requested_base_ref": args.base_ref,
        "resolved_base_ref": resolved_base_ref,
        "worktree_head": "",
        "worktree_detached": False,
        "cluster_uri": args.cluster_uri,
        "trace_url": args.trace_url,
        "loopback_port": cluster_port,
        "preexisting_listener_pids": preexisting_listener_pids,
        "preexisting_processes_preserved": True,
        "build_launcher_pid": 0,
        "build_owned_process_ids": [],
        "build_job_object_assigned": False,
        "build_timed_out": False,
        "build_all_processes_exited": False,
        "service_launcher_pid": 0,
        "service_pid": 0,
        "service_owned_process_ids": [],
        "service_job_object_assigned": False,
        "service_all_processes_exited": False,
        "request_scope": request_scope,
        "command": command,
        "non_executing": True,
        "supplied_query_executed": False,
        "primary_head_before": primary_head_before,
        "primary_head_after": "",
        "primary_head_tree": primary_head_tree,
        "primary_index_tree_before": primary_index_tree_before,
        "primary_index_tree_after": "",
        "primary_status_before_clean": True,
        "primary_status_after_clean": False,
        "service_stopped": False,
        "port_released": False,
        "worktree_removed": False,
        "worktree_root_removed": False,
        "worktree_registration_removed": False,
        "cleanup_finally": False,
        "outcome": "failed",
        "failure": "",
        "trace_output_digest_sha256": "",
    }
    build_process: SuspendedProcess | None = None
    process: SuspendedProcess | None = None
    build_job: WindowsJob | None = None
    service_job: WindowsJob | None = None
    error: Exception | None = None
    worktree_added = False
    worktree_add_attempted = False
    ownership_token = ""
    ownership_created = False
    try:
        (
            ownership_marker,
            ownership_token,
            receipt["ownership_marker_digest_sha256"],
        ) = _create_owned_worktree_root(worktree_root)
        ownership_created = True
        worktree_add_attempted = True
        subprocess.run(
            [
                "git",
                "-C",
                str(primary),
                "worktree",
                "add",
                "--detach",
                str(worktree),
                resolved_base_ref,
            ],
            check=True,
            capture_output=True,
        )
        worktree_added = True
        receipt["worktree_head"] = _git(worktree, "rev-parse", "HEAD")
        receipt["worktree_detached"] = (
            subprocess.run(
                ["git", "-C", str(worktree), "symbolic-ref", "-q", "HEAD"],
                capture_output=True,
            ).returncode
            != 0
        )
        if (
            receipt["worktree_head"] != primary_head_before
            or not receipt["worktree_detached"]
        ):
            raise LocalTraceDriverError(
                "Disposable worktree is not detached at the primary checkout HEAD."
            )
        subprocess.run(
            ["git", "-C", str(worktree), "apply", "--check", str(patch)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "apply", str(patch)],
            check=True,
            capture_output=True,
        )
        build_job = WindowsJob()
        build_process = SuspendedProcess(
            build_command,
            cwd=worktree,
        )
        receipt["build_launcher_pid"] = build_process.pid
        build_job.assign(build_process)
        receipt["build_job_object_assigned"] = True
        build_process.resume()
        try:
            build_result = build_process.wait(timeout=args.build_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            receipt["build_timed_out"] = True
            raise LocalTraceDriverError(
                f"Local build timed out after {args.build_timeout_seconds} seconds."
            ) from exc
        if build_result != 0:
            raise LocalTraceDriverError(
                f"Repository-supported local build failed with exit code {build_result}."
            )
        build_owned = {build_process.pid, *_descendant_pids(build_process.pid)}
        receipt["build_owned_process_ids"] = sorted(build_owned)
        if not build_job.terminate_and_wait(5):
            raise LocalTraceDriverError("Build Job Object retained live processes.")
        receipt["build_all_processes_exited"] = not _existing_pids(
            receipt["build_owned_process_ids"]
        )
        if not receipt["build_all_processes_exited"]:
            raise LocalTraceDriverError("Not every owned build process exited.")
        build_job.close()
        build_job = None
        environment = os.environ.copy()
        environment.update(
            {
                "KUSTO_OPTIMIZER_TRACE_SCOPE": request_scope,
                "KUSTO_OPTIMIZER_TRACE_NON_EXECUTING_ONLY": "1",
                "KUSTO_LOCAL_SERVICE_URI": args.cluster_uri,
            }
        )
        service_job = WindowsJob()
        process = SuspendedProcess(
            service_command,
            cwd=worktree,
            env=environment,
        )
        receipt["service_launcher_pid"] = process.pid
        service_job.assign(process)
        receipt["service_job_object_assigned"] = True
        process.resume()
        deadline = time.monotonic() + args.startup_timeout_seconds
        listener_pids: list[int] = []
        while time.monotonic() < deadline:
            listener_pids = _listener_pids(cluster_port)
            if listener_pids:
                break
            if process.poll() is not None and not _descendant_pids(process.pid):
                raise LocalTraceDriverError("Local service exited before opening its endpoint.")
            time.sleep(0.2)
        if len(listener_pids) != 1:
            raise LocalTraceDriverError(
                "Local service did not acquire exactly one isolated loopback listener."
            )
        owned = {process.pid, *_descendant_pids(process.pid)}
        if not set(listener_pids) <= owned:
            raise LocalTraceDriverError(
                "Loopback listener is not owned by the driver-started local service."
            )
        receipt["service_owned_process_ids"] = sorted(owned)
        receipt["service_pid"] = listener_pids[0]
        request_body = json.dumps(
            {
                "database": args.database,
                "command": command,
                "request_scope": request_scope,
                "non_executing": True,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            args.trace_url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request, timeout=args.request_timeout_seconds
        ) as response:
            response_bytes = response.read()
        if not response_bytes.strip():
            raise LocalTraceDriverError("Local trace endpoint returned an empty response.")
        trace_output.parent.mkdir(parents=True, exist_ok=True)
        trace_output.write_bytes(response_bytes)
        receipt["trace_output_digest_sha256"] = hashlib.sha256(
            response_bytes
        ).hexdigest()
        receipt["outcome"] = "captured"
    except Exception as exc:
        error = exc
        receipt["failure"] = str(exc)
    finally:
        cleanup_errors: list[str] = []
        if build_job is not None:
            try:
                if build_process is not None:
                    build_owned = {
                        build_process.pid,
                        *_descendant_pids(build_process.pid),
                    }
                    receipt["build_owned_process_ids"] = sorted(
                        set(receipt["build_owned_process_ids"]) | build_owned
                    )
                if not build_job.terminate_and_wait(5):
                    cleanup_errors.append("build Job Object retained live processes")
            except Exception as exc:
                cleanup_errors.append(f"build process cleanup failed: {exc}")
            finally:
                try:
                    build_job.close()
                except Exception as exc:
                    cleanup_errors.append(f"build Job Object close failed: {exc}")
        if build_process is not None:
            try:
                build_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cleanup_errors.append("build launcher did not stop within 5 seconds")
        try:
            remaining_build = _existing_pids(receipt["build_owned_process_ids"])
            if remaining_build:
                _stop_exact_pids(remaining_build)
            receipt["build_all_processes_exited"] = not _existing_pids(
                receipt["build_owned_process_ids"]
            )
        except Exception as exc:
            cleanup_errors.append(f"build process exit verification failed: {exc}")
        if build_process is not None:
            try:
                build_process.close()
            except Exception as exc:
                cleanup_errors.append(f"build process handle close failed: {exc}")
        if process is not None:
            try:
                owned = {process.pid, *_descendant_pids(process.pid)}
            except Exception as exc:
                owned = {process.pid}
                cleanup_errors.append(f"process inventory failed: {exc}")
            receipt["service_owned_process_ids"] = sorted(
                set(receipt["service_owned_process_ids"]) | owned
            )
            try:
                if service_job is None:
                    _stop_exact_pids(sorted(owned, reverse=True))
                elif not service_job.terminate_and_wait(5):
                    cleanup_errors.append("service Job Object retained live processes")
            except Exception as exc:
                cleanup_errors.append(f"service process cleanup failed: {exc}")
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cleanup_errors.append("launcher process did not stop within 5 seconds")
        if service_job is not None:
            try:
                service_job.close()
            except Exception as exc:
                cleanup_errors.append(f"service Job Object close failed: {exc}")
        try:
            remaining_owned = _existing_pids(receipt["service_owned_process_ids"])
            if remaining_owned:
                _stop_exact_pids(remaining_owned)
                remaining_owned = _existing_pids(
                    receipt["service_owned_process_ids"]
                )
            receipt["service_all_processes_exited"] = not remaining_owned
        except Exception as exc:
            remaining_owned = receipt["service_owned_process_ids"]
            cleanup_errors.append(f"service process exit verification failed: {exc}")
        if process is not None:
            try:
                process.close()
            except Exception as exc:
                cleanup_errors.append(f"service process handle close failed: {exc}")
        try:
            remaining_listener_pids = _listener_pids(cluster_port)
        except Exception as exc:
            remaining_listener_pids = remaining_owned
            cleanup_errors.append(f"listener verification failed: {exc}")
        receipt["service_stopped"] = receipt["service_all_processes_exited"]
        if worktree_add_attempted:
            try:
                removal = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(primary),
                        "worktree",
                        "remove",
                        "--force",
                        str(worktree),
                    ],
                    capture_output=True,
                    text=True,
                )
                receipt["worktree_removed"] = (
                    removal.returncode == 0 and not worktree.exists()
                )
                subprocess.run(
                    ["git", "-C", str(primary), "worktree", "prune"],
                    check=True,
                    capture_output=True,
                )
                receipt["worktree_removed"] = not worktree.exists()
                receipt["worktree_registration_removed"] = not _worktree_registered(
                    primary, worktree
                )
                if not receipt["worktree_registration_removed"]:
                    cleanup_errors.append(
                        f"disposable worktree registration cleanup failed: {removal.stderr.strip()}"
                    )
            except Exception as exc:
                cleanup_errors.append(
                    f"disposable worktree registration cleanup failed: {exc}"
                )
        else:
            receipt["worktree_removed"] = not worktree.exists()
            receipt["worktree_registration_removed"] = not _worktree_registered(
                primary, worktree
            )
        if ownership_created and worktree_root.exists():
            receipt["ownership_marker_validated"] = _owned_root_marker_matches(
                worktree_root, ownership_marker, ownership_token
            )
            if receipt["ownership_marker_validated"]:
                try:
                    shutil.rmtree(worktree_root)
                except Exception as exc:
                    cleanup_errors.append(
                        f"owned worktree root cleanup failed: {exc}"
                    )
            else:
                cleanup_errors.append(
                    "worktree ownership marker changed; refusing recursive deletion"
                )
        else:
            receipt["ownership_marker_validated"] = ownership_created
        receipt["worktree_root_removed"] = not worktree_root.exists()
        receipt["worktree_removed"] = not worktree.exists()
        receipt["port_released"] = not remaining_listener_pids
        try:
            receipt["primary_head_after"] = _git(primary, "rev-parse", "HEAD")
            primary_status_after = _git(
                primary, "status", "--porcelain=v1", "--untracked-files=all"
            )
            receipt["primary_status_after_clean"] = not bool(primary_status_after)
            receipt["primary_index_tree_after"] = _git(primary, "write-tree")
        except Exception as exc:
            cleanup_errors.append(f"primary checkout verification failed: {exc}")
        receipt["cleanup_finally"] = True
        if (
            receipt["primary_head_after"] != receipt["primary_head_before"]
            or receipt["primary_index_tree_before"] != receipt["primary_head_tree"]
            or receipt["primary_index_tree_after"]
            != receipt["primary_index_tree_before"]
            or receipt["primary_status_before_clean"] is not True
            or receipt["primary_status_after_clean"] is not True
            or not receipt["service_stopped"]
            or not receipt["service_all_processes_exited"]
            or not receipt["build_all_processes_exited"]
            or not receipt["port_released"]
            or not receipt["worktree_removed"]
            or not receipt["worktree_root_removed"]
            or not receipt["worktree_registration_removed"]
            or not receipt["ownership_marker_validated"]
        ):
            cleanup_errors.append("cleanup/restoration invariants failed")
        if cleanup_errors:
            receipt["outcome"] = "failed"
            cleanup_failure = "; ".join(cleanup_errors)
            receipt["failure"] = "; ".join(
                item for item in (receipt["failure"], cleanup_failure) if item
            )
            error = LocalTraceDriverError(receipt["failure"])
        digest_source = dict(receipt)
        receipt["receipt_digest_sha256"] = _canonical_digest(digest_source)
        receipt_file.parent.mkdir(parents=True, exist_ok=True)
        receipt_file.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if error is not None:
        raise LocalTraceDriverError(str(error)) from error
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Acquire optimizer trace evidence from an isolated local worktree/service."
    )
    parser.add_argument("--primary-checkout", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--base-ref", default="HEAD")
    parser.add_argument("--instrumentation-patch", required=True)
    parser.add_argument("--build-command-json", required=True)
    parser.add_argument("--service-command-json", required=True)
    parser.add_argument("--cluster-uri", required=True)
    parser.add_argument("--trace-url", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--query-file", required=True)
    parser.add_argument("--request-scope", required=True)
    parser.add_argument("--trace-output", required=True)
    parser.add_argument("--receipt-file", required=True)
    parser.add_argument("--build-timeout-seconds", type=float, default=1800)
    parser.add_argument("--startup-timeout-seconds", type=float, default=60)
    parser.add_argument("--request-timeout-seconds", type=float, default=60)
    args = parser.parse_args()
    try:
        receipt = run_local_trace(args)
    except (
        LocalTraceDriverError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(
        json.dumps(
            {
                "ok": receipt["outcome"] == "captured",
                "outcome": receipt["outcome"],
                "receipt_digest_sha256": receipt["receipt_digest_sha256"],
                "cleanup_complete": (
                    receipt["cleanup_finally"]
                    and receipt["build_all_processes_exited"]
                    and receipt["service_all_processes_exited"]
                    and receipt["worktree_removed"]
                    and receipt["worktree_root_removed"]
                    and receipt["worktree_registration_removed"]
                    and receipt["ownership_marker_validated"]
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
