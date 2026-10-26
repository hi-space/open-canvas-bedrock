"""Project-scoped filesystem operations shared by all API workers via NFS locks."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from fastapi import HTTPException

from api.workspaces.html_documents import is_html_path, prepare_html
from api.workspaces.persistence import Metadata, atomic_bytes, write_json

MAX_BYTES = 2 * 1024 * 1024
MAX_CHARACTERS = 200000
EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm"}


def now():
    return int(time.time() * 1000)


def version(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_path(value: str) -> str:
    parts = value.split("/")
    if (
        not value or len(value) > 500 or len(parts) > 8 or "\\" in value
        or any(not part or part.startswith(".") or ":" in part for part in parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or Path(value).suffix.lower() not in EXTENSIONS
        or any(len(part.encode("utf-8")) > 240 for part in parts)
    ):
        raise HTTPException(422, "경로는 숨김 폴더나 상위 경로가 없는 Markdown/TXT/HTML 파일이어야 합니다.")
    return value


def validate_content(content):
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError:
        raise HTTPException(422, "올바른 UTF-8 문서를 사용해 주세요.") from None
    if len(encoded) > MAX_BYTES or len(content) > MAX_CHARACTERS or "\x00" in content:
        raise HTTPException(422, "문서는 UTF-8 텍스트, 2MB 및 200,000자 이내여야 합니다.")
    return encoded


class ProjectFiles:
    def __init__(self, owner, workspace=None):
        if not re.fullmatch(r"[a-f0-9]{64}", owner):
            raise HTTPException(401, "작업 공간 사용자를 확인하지 못했습니다.")
        if workspace is not None and not re.fullmatch(r"[a-f0-9-]{36}", workspace):
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        self.root = Path(os.environ.get("WORKSPACE_ROOT", "/mnt/workspace")).absolute()
        self.owner = owner
        self.workspace = workspace
        self.owner_namespace = "canvas-workspaces:" + owner
        self.namespace = f"canvas-workspace:{owner}:{workspace}"
        self.directory = self.root / owner / (workspace or "_owner")
        self.files = self.directory / "files"
        self.internal = self.directory / ".canvas"
        self.metadata = Metadata(self.root)

    def safe(self, path: Path):
        if not path.is_relative_to(self.root):
            raise HTTPException(422, "프로젝트 밖의 파일에 접근할 수 없습니다.")
        cursor = self.root
        if cursor.is_symlink():
            raise HTTPException(422, "심볼릭 링크 경로를 사용할 수 없습니다.")
        for part in path.relative_to(self.root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise HTTPException(422, "심볼릭 링크 경로를 사용할 수 없습니다.")
        return path

    @contextmanager
    def lock(self):
        directory = self.safe(self.internal)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(directory / "write.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        deadline = time.monotonic() + 10
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise HTTPException(409, "다른 저장이 진행 중입니다. 잠시 후 다시 시도해 주세요.")
                    time.sleep(0.03)
            from api.workspaces.proposals import recover_approval
            recover_approval(self)
            yield
        finally:
            os.close(descriptor)

    def require(self):
        workspace = self.metadata.get(self.owner_namespace, self.workspace)
        if not workspace:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        return workspace

    def path(self, path):
        return self.safe(self.files / validate_path(path))

    def read(self, path, missing=False):
        target = self.path(path)
        try:
            descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                data = stream.read(MAX_BYTES + 1)
                stat = os.fstat(stream.fileno())
        except FileNotFoundError:
            if missing:
                return None
            raise HTTPException(404, "문서가 없습니다.") from None
        except (IsADirectoryError, OSError):
            raise HTTPException(422, "문서 파일을 읽을 수 없습니다.") from None
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(422, "UTF-8 문서를 사용해 주세요.") from None
        validate_content(content)
        return {
            "path": path, "name": target.name, "content": content,
            "version": version(content), "bytes": len(data), "updatedAt": int(stat.st_mtime * 1000),
        }

    def list(self):
        if not self.files.exists():
            return []
        result = []
        for parent, directories, names in os.walk(self.safe(self.files), followlinks=False):
            directories[:] = sorted(
                directory for directory in directories
                if not directory.startswith(".") and not (Path(parent) / directory).is_symlink()
            )
            for name in sorted(names):
                if name.startswith(".") or Path(name).suffix.lower() not in EXTENSIONS:
                    continue
                path = (Path(parent) / name).relative_to(self.files).as_posix()
                try:
                    document = self.read(path)
                except HTTPException:
                    continue
                result.append({key: value for key, value in document.items() if key != "content"})
                if len(result) > 200:
                    raise HTTPException(422, "프로젝트 문서는 최대 200개입니다.")
        return sorted(result, key=lambda item: item["path"].casefold())

    def _history_path(self, path):
        return self.safe(self.internal / "history" / f"{hashlib.sha256(path.encode()).hexdigest()}.json")

    def history(self, path):
        validate_path(path)
        target = self._history_path(path)
        return json.loads(target.read_bytes()) if target.exists() else []

    def save(self, path, content, expected, label="직접 저장"):
        # Caller holds project lock for both the compare and atomic replacement.
        data = validate_content(content)
        target = self.path(path)
        previous = self.read(path, missing=True)
        if (previous["version"] if previous else None) != expected:
            raise HTTPException(409, "파일이 다른 곳에서 변경되었습니다. 최신 내용과 비교한 뒤 저장해 주세요.")
        if previous is None and len(self.list()) >= 200:
            raise HTTPException(422, "프로젝트 문서는 최대 200개입니다.")
        if is_html_path(path):
            try:
                content = prepare_html(content)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            # Added IDs also count toward the stored file and model context limits.
            data = validate_content(content)
        if previous is not None and previous["content"] == content:
            return previous
        if previous:
            revisions = self.history(path)
            revisions.append({
                "id": str(uuid.uuid4()), "content": previous["content"],
                "label": label + " 전", "createdAt": now(),
            })
            write_json(self._history_path(path), revisions[-30:])
        atomic_bytes(target, data)
        return self.read(path)

    def proposal_path(self, proposal_id):
        if not re.fullmatch(r"[a-f0-9-]{36}", proposal_id):
            raise HTTPException(404, "수정안을 찾을 수 없습니다.")
        return self.safe(self.internal / "proposals" / (proposal_id + ".json"))

    def proposal(self, proposal_id):
        path = self.proposal_path(proposal_id)
        if not path.exists():
            raise HTTPException(404, "수정안을 찾을 수 없습니다.")
        return json.loads(path.read_bytes())

    def put_proposal(self, proposal):
        write_json(self.proposal_path(proposal["id"]), proposal)
        summary = {
            key: proposal[key] for key in
            ["id", "jobId", "path", "explanation", "createdAt", "status"]
        } | {"pendingCount": sum(change["decision"] == "pending" for change in proposal["changes"])}
        if proposal.get("savedCopy"):
            summary["savedCopy"] = proposal["savedCopy"]
        if proposal.get("sourceSnapshot"):
            summary["sourceSnapshot"] = proposal["sourceSnapshot"]
            if "sourceReads" in proposal:
                summary["sourceVersions"] = [item["version"] for item in proposal["sourceReads"]]
        self.metadata.put(self.namespace, "proposal:" + proposal["id"], summary)
