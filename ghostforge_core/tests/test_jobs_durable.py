from __future__ import annotations

from ghostforge_core.jobs import JobStore
from ghostforge_core.types import JobSpec, JobStatus


def test_running_jobs_marked_interrupted_on_restart(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    store = JobStore(db_path)
    job = store.submit("stub", JobSpec(prompt="slow"))
    store.start(job.id)

    restarted = JobStore(db_path)
    recovered = restarted.get(job.id)

    assert recovered.status == JobStatus.failed
    assert recovered.error is not None
    assert recovered.error.code == "interrupted"
