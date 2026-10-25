"""Slow external work holds its job lease; finished or dead workers cannot renew it."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import time

from fastapi import HTTPException
import pytest

from api.workspaces import jobs, routes, service
from api.workspaces.files import ProjectFiles
from api.workspaces.models import ChatRequest


class Clock:
    value = 1_000_000

    def __call__(self):
        return self.value


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_METADATA", "file")
    monkeypatch.setenv("WORKSPACE_AUTH_MODE", "local")
    monkeypatch.setattr(jobs, "JOB_HEARTBEAT_SECONDS", 0.01)
    clock = Clock()
    for module in (jobs, routes, service):
        monkeypatch.setattr(module, "now", clock)
    files = ProjectFiles(hashlib.sha256(b"heartbeat-test").hexdigest(),
                         "00000000-0000-0000-0000-000000000001")
    with files.lock():
        files.metadata.put(files.owner_namespace, files.workspace, {"id": files.workspace})
    monkeypatch.setattr(service, "fetch_requested_sources", lambda *_args: [])
    return files, clock


def prepare(files, request_id="request-1"):
    with files.lock():
        return service.prepare_job(files, ChatRequest(message="Revise.", requestId=request_id))


def read_job(files, job_id):
    with files.lock():
        return files.metadata.get(files.namespace, "job:" + job_id)


def wait_for_heartbeat(files, job_id, timestamp):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        job = read_job(files, job_id)
        if job["updatedAt"] >= timestamp:
            return job
        threading.Event().wait(0.005)
    pytest.fail("The running job did not renew its timestamp.")


def assert_heartbeat_stopped(job_id):
    assert not any(
        thread.name == f"workspace-job-heartbeat-{job_id}" and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_long_prefetch_and_runtime_remain_busy_past_the_original_stale_window(project, monkeypatch):
    files, clock = project
    job, payload = prepare(files)
    fetching, invoking = threading.Event(), threading.Event()
    fetched, returned = threading.Event(), threading.Event()

    def fetch(*_args):
        fetching.set()
        assert fetched.wait(3)
        return []

    def invoke(_payload):
        invoking.set()
        assert returned.wait(3)
        return {"message": "Prepared for review.", "proposals": []}

    monkeypatch.setattr(service, "fetch_requested_sources", fetch)
    monkeypatch.setattr(service, "invoke_agent", invoke)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.run_job, files.owner, files.workspace, job["id"], payload)
        try:
            assert fetching.wait(1)
            clock.value += 700_000
            wait_for_heartbeat(files, job["id"], clock.value)
            fetched.set()
            assert invoking.wait(1)
            clock.value += 700_000
            running = wait_for_heartbeat(files, job["id"], clock.value)
            assert clock.value - job["createdAt"] > 900_000
            assert routes.expire_job(running)["status"] == "running"
            with pytest.raises(HTTPException) as busy:
                prepare(files, "duplicate-while-running")
            assert busy.value.status_code == 409
        finally:
            fetched.set()
            returned.set()
        future.result(timeout=2)
    assert read_job(files, job["id"])["status"] == "completed"
    assert_heartbeat_stopped(job["id"])


class WorkerCrash(BaseException):
    pass


@pytest.mark.parametrize("outcome", ["success", "failure", "crash"])
def test_heartbeat_stops_on_every_job_exit_and_crashed_jobs_still_expire(project, monkeypatch, outcome):
    files, clock = project
    job, payload = prepare(files)

    def invoke(_payload):
        clock.value += 700_000
        wait_for_heartbeat(files, job["id"], clock.value)
        if outcome == "failure":
            raise RuntimeError("provider unavailable")
        if outcome == "crash":
            raise WorkerCrash()
        return {"message": "Prepared for review.", "proposals": []}

    monkeypatch.setattr(service, "invoke_agent", invoke)
    if outcome == "crash":
        with pytest.raises(WorkerCrash):
            service.run_job(files.owner, files.workspace, job["id"], payload)
    else:
        service.run_job(files.owner, files.workspace, job["id"], payload)
    stored = read_job(files, job["id"])
    assert stored["status"] == {"success": "completed", "failure": "failed", "crash": "running"}[outcome]
    assert_heartbeat_stopped(job["id"])
    clock.value += 900_001
    assert read_job(files, job["id"])["updatedAt"] == stored["updatedAt"]
    if outcome == "crash":
        assert routes.expire_job(stored)["status"] == "failed"
        assert prepare(files, "retry-after-crash")[0]["id"] != job["id"]


def test_heartbeats_preserve_progress_and_cannot_resurrect_a_terminal_job(project, monkeypatch):
    files, clock = project
    job, payload = prepare(files)

    def invoke(_payload):
        service.report_progress(files, job["id"], "출처를 확인하고 있습니다.")
        clock.value += 700_000
        renewed = wait_for_heartbeat(files, job["id"], clock.value)
        assert renewed["message"] == "출처를 확인하고 있습니다."
        with files.lock():
            stopped = files.metadata.get(files.namespace, "job:" + job["id"])
            stopped.update(status="failed", error="Already stopped.")
            files.metadata.put(files.namespace, "job:" + job["id"], stopped)
        clock.value += 10_000
        return {"message": "A late result.", "proposals": []}

    monkeypatch.setattr(service, "invoke_agent", invoke)
    service.run_job(files.owner, files.workspace, job["id"], payload)
    stopped = read_job(files, job["id"])
    assert stopped["status"] == "failed"
    assert stopped["error"] == "Already stopped."
    assert not any(
        key.startswith("message:") and value["role"] == "assistant"
        for key, value in files.metadata.items(files.namespace).items()
    )
    assert_heartbeat_stopped(job["id"])


@pytest.mark.parametrize("status", ["running", "completed", "failed"])
def test_only_a_queued_job_can_be_started(project, monkeypatch, status):
    files, _clock = project
    job, payload = prepare(files)
    with files.lock():
        previous = {**job, "status": status}
        files.metadata.put(files.namespace, "job:" + job["id"], previous)
    calls = []
    monkeypatch.setattr(service, "invoke_agent",
                        lambda _payload: calls.append("called") or {"message": "Late.", "proposals": []})
    service.run_job(files.owner, files.workspace, job["id"], payload)
    assert calls == []
    assert read_job(files, job["id"]) == previous
    assert_heartbeat_stopped(job["id"])


def test_a_failure_before_claiming_the_job_cannot_fail_another_worker(project, monkeypatch):
    files, _clock = project
    job, payload = prepare(files)
    with files.lock():
        running = {**job, "status": "running"}
        files.metadata.put(files.namespace, "job:" + job["id"], running)

    def unavailable(_files):
        raise RuntimeError("project metadata temporarily unavailable")

    monkeypatch.setattr(ProjectFiles, "require", unavailable)
    service.run_job(files.owner, files.workspace, job["id"], payload)
    assert read_job(files, job["id"]) == running
    assert_heartbeat_stopped(job["id"])


@pytest.mark.parametrize("status", ["queued", "running"])
def test_stale_boundary_is_consistent_for_job_display_and_new_requests(project, status):
    files, clock = project
    job, _payload = prepare(files)
    with files.lock():
        job["status"] = status
        files.metadata.put(files.namespace, "job:" + job["id"], job)
    clock.value += 900_000
    assert routes.expire_job(job)["status"] == "failed"
    assert prepare(files, "retry-stale")[0]["id"] != job["id"]


def test_expired_progress_cannot_renew_a_job_after_a_replacement_is_admitted(project):
    files, clock = project
    job, _payload = prepare(files)
    with files.lock():
        expired = {**job, "status": "running"}
        files.metadata.put(files.namespace, "job:" + job["id"], expired)
    clock.value += 900_000
    replacement, _payload = prepare(files, "replacement")
    service.report_progress(files, job["id"], "Late research progress.")
    assert read_job(files, job["id"]) == expired
    assert routes.expire_job(read_job(files, job["id"]))["status"] == "failed"
    assert read_job(files, replacement["id"]) == replacement


def test_fresh_progress_updates_the_message_and_timestamp(project):
    files, clock = project
    job, _payload = prepare(files)
    with files.lock():
        running = {**job, "status": "running"}
        files.metadata.put(files.namespace, "job:" + job["id"], running)
    clock.value += 899_999
    service.report_progress(files, job["id"], "출처를 확인하고 있습니다.")
    assert read_job(files, job["id"]) == {
        **running, "message": "출처를 확인하고 있습니다.", "updatedAt": clock.value,
    }


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_progress_leaves_terminal_jobs_unchanged(project, status):
    files, clock = project
    job, _payload = prepare(files)
    with files.lock():
        terminal = {**job, "status": status}
        files.metadata.put(files.namespace, "job:" + job["id"], terminal)
    clock.value += 100
    service.report_progress(files, job["id"], "Late progress.")
    assert read_job(files, job["id"]) == terminal
