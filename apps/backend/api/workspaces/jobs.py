"""Shared workspace job liveness policy."""
import logging
import threading

from api.workspaces.files import now


logger = logging.getLogger(__name__)
JOB_STALE_AFTER_MS = 15 * 60 * 1000
JOB_HEARTBEAT_SECONDS = 60


class JobHeartbeat:
    """Renew one live job until its worker exits or loses the lease."""

    def __init__(self, files, job_id):
        self.files = files
        self.job_id = job_id
        self._stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"workspace-job-heartbeat-{job_id}", daemon=True,
        )

    def start(self):
        self._thread.start()

    def stop(self):
        self._stopped.set()
        if self._thread.ident is not None:
            self._thread.join()

    def _run(self):
        while not self._stopped.wait(JOB_HEARTBEAT_SECONDS):
            try:
                with self.files.lock():
                    if self._stopped.is_set():
                        return
                    job = self.files.metadata.get(self.files.namespace, "job:" + self.job_id)
                    timestamp = now()
                    if (
                        self._stopped.is_set() or not job or job["status"] != "running"
                        or job_is_stale(job, timestamp)
                    ):
                        return
                    # Fetch the latest record; preserve research progress and all other fields.
                    job["updatedAt"] = timestamp
                    self.files.metadata.put(self.files.namespace, "job:" + self.job_id, job)
            except Exception as error:
                logger.warning("Workspace job heartbeat failed (%s)", type(error).__name__)


def job_is_stale(job, timestamp):
    return (
        job["status"] in {"queued", "running"}
        and timestamp - job["updatedAt"] >= JOB_STALE_AFTER_MS
    )
