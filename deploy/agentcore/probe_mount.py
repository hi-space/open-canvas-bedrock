"""Run inside a Fargate task with the native S3 Files API access-point mount.

Creates a synthetic, isolated project. By default it removes that project after
checking NFS, advisory locks, atomic replacement, and exact UTF-8 bytes. --keep
retains the fixture and emits its context for a subsequent AgentCore read probe.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


LOCK_CHILD = """
import fcntl, sys
with open(sys.argv[1], 'a+b') as lock:
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(23)
"""


def mount_type(root):
    """Identify the containing mount without printing unrelated mount details."""
    selected = ("", "")
    with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
        for line in mounts:
            before, separator, after = line.partition(" - ")
            if not separator:
                continue
            point = before.split()[4].replace("\\040", " ").replace("\\134", "\\")
            if str(root) == point or str(root).startswith(point.rstrip("/") + "/"):
                if len(point) > len(selected[0]):
                    selected = (point, after.split()[0])
    return {"path": selected[0], "type": selected[1]}


def write_durable(path, content):
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)


def run_probe(root, *, require_nfs=True, keep=False):
    root = Path(root).resolve(strict=True)
    filesystem = mount_type(root)
    if require_nfs and filesystem["type"] not in {"nfs", "nfs4"}:
        raise RuntimeError(f"Expected the native NFS mount; observed {filesystem['type'] or 'unknown'}.")
    owner_key = hashlib.sha256(f"canvas-mount-probe:{uuid.uuid4()}".encode()).hexdigest()
    workspace_id = str(uuid.uuid4())
    owner_root = root / owner_key
    owner_root.mkdir(mode=0o750)
    succeeded = False
    try:
        project = owner_root / workspace_id
        files = project / "files"
        metadata = project / ".canvas"
        project.mkdir(mode=0o750)
        files.mkdir(mode=0o750)
        metadata.mkdir(mode=0o700)
        lock_path = metadata / "probe.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            blocked = subprocess.run(
                [sys.executable, "-c", LOCK_CHILD, str(lock_path)],
                timeout=10, check=False, capture_output=True,
            )
            if blocked.returncode != 23:
                raise RuntimeError(f"Another process bypassed the held file lock (exit {blocked.returncode}).")
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        released = subprocess.run(
            [sys.executable, "-c", LOCK_CHILD, str(lock_path)],
            timeout=10, check=False, capture_output=True,
        )
        if released.returncode != 0:
            raise RuntimeError(f"The released file lock stayed locked (exit {released.returncode}).")

        path = files / "mount-probe.md"
        original = "\ufeff원본\r\nCafe\u0301 · 😀\n".encode("utf-8")
        replacement = (
            "\ufeff# S3 Files mount probe\r\n"
            "한글 · Cafe\u0301 · 😀 · 👨‍👩‍👦\r\n"
            f"Unique marker: {uuid.uuid4()}\n"
        ).encode("utf-8")
        write_durable(path, original)
        temporary = files / ".mount-probe.tmp"
        with path.open("rb") as old_reader:
            write_durable(temporary, replacement)
            os.replace(temporary, path)
            if old_reader.read() != original:
                raise RuntimeError("Atomic replacement changed an already-open original reader.")
        reopened = path.read_bytes()
        if reopened != replacement:
            raise RuntimeError("A new reader did not see the exact replacement bytes.")
        if reopened.decode("utf-8").encode("utf-8") != replacement:
            raise RuntimeError("UTF-8 round trip changed document content.")
        if temporary.exists():
            raise RuntimeError("Atomic replacement left the staged filename in place.")
        stat = path.stat()
        result = {
            "ok": True,
            "filesystem": filesystem,
            "lockConflict": True,
            "lockRelease": True,
            "atomicReplacement": True,
            "exactUtf8": True,
            "retained": keep,
            "ownerKey": owner_key,
            "workspaceId": workspace_id,
            "path": path.name,
            "version": hashlib.sha256(reopened).hexdigest(),
            "bytes": len(reopened),
            "uid": stat.st_uid,
            "gid": stat.st_gid,
            "content": reopened.decode("utf-8"),
        }
        succeeded = True
        return result
    finally:
        if not (keep and succeeded):
            shutil.rmtree(owner_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("WORKSPACE_ROOT", "/mnt/workspace")))
    parser.add_argument("--keep", action="store_true", help="Retain the synthetic project for an AgentCore read check")
    parser.add_argument("--allow-local", action="store_true", help="Local test only: do not require NFS")
    args = parser.parse_args()
    try:
        result = run_probe(args.root, require_nfs=not args.allow_local, keep=args.keep)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
