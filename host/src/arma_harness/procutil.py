"""Process helpers: spawning that survives the caller, liveness, and teardown."""
from __future__ import annotations

import contextlib
import ctypes
import subprocess
import time
from pathlib import Path

import psutil

_DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS


def in_job() -> bool:
    k32 = ctypes.windll.kernel32
    # The pseudo-handle (-1) must not be truncated to 32 bits, so the signatures matter.
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    result = ctypes.c_int(0)
    k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(result))
    return bool(result.value)


def spawn(args: list[str], cwd: Path) -> int:
    """Start a detached process that outlives us.

    MCP clients run their servers inside a KILL_ON_JOB_CLOSE job (the Python SDK does, and venv
    launchers nest another one); CREATE_BREAKAWAY_FROM_JOB was observed to report success yet die
    with the outer job. Inside a job we therefore create the process through WMI, which starts it
    from the WMI service, outside every job.
    """
    if not in_job():
        return subprocess.Popen(args, cwd=cwd, creationflags=_DETACHED,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid
    cmdline = subprocess.list2cmdline(args).replace("'", "''")
    cwd_q = str(cwd).replace("'", "''")
    ps = (f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
          f"@{{CommandLine='{cmdline}'; CurrentDirectory='{cwd_q}'}}; "
          f"if ($r.ReturnValue -ne 0) {{ Write-Error \"Win32_Process.Create returned $($r.ReturnValue)\"; exit 1 }}; "
          f"$r.ProcessId")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                         capture_output=True, text=True, timeout=60)
    pid = out.stdout.strip()
    if out.returncode != 0 or not pid.isdigit():
        raise RuntimeError(f"WMI spawn failed: {(out.stderr or out.stdout).strip()[:500]}")
    return int(pid)


def alive(pid: int | None, image: str | None = None) -> bool:
    """True if the pid exists (and, when given, runs an executable with that file name)."""
    if not pid:
        return False
    try:
        p = psutil.Process(pid)
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return False
        return image is None or p.name().lower() == image.lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def kill_tree(pid: int, timeout: float = 10) -> bool:
    """Terminate a process and its children. Returns True if it is gone."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True
    procs = [parent, *parent.children(recursive=True)]
    for p in procs:
        with contextlib.suppress(psutil.NoSuchProcess):
            p.kill()
    try:
        _, still = psutil.wait_procs(procs, timeout=timeout)
    except psutil.AccessDenied:
        # Windows can let us kill a process we may not wait on: a server started through WMI, outside our job. Its
        # stop then crashed after the kill had worked. Watch for it to be gone instead.
        deadline = time.time() + timeout
        still = procs
        while still and time.time() < deadline:
            still = [p for p in still if psutil.pid_exists(p.pid)]
            if still:
                time.sleep(0.2)
    return not still


def find_processes(image: str) -> list[psutil.Process]:
    out = []
    for p in psutil.process_iter(["name", "pid", "create_time"]):
        if (p.info["name"] or "").lower() == image.lower():
            out.append(p)
    return out
