from __future__ import annotations

import time

from ghostforge_core.jobs import JobRunner, JobStore
from ghostforge_core.types import JobSpec, JobStatus


def test_runner_with_dispatch_false_records_but_does_not_run(tmp_path):
    """Adapters that share a SQLite store with another owner must record jobs
    without dispatching them, so exactly one process runs the job loop."""
    store = JobStore(tmp_path / "jobs.sqlite")
    runner = JobRunner(store, max_workers=1, dispatch=False)

    ran: list[bool] = []

    def handler(spec, reporter, cancel):
        ran.append(True)
        return {"ok": True}

    runner.register("noop", JobSpec, handler)
    handle = runner.submit("noop", JobSpec(prompt="should not run"))
    time.sleep(0.2)

    job = store.get(handle.id)
    assert job.status == JobStatus.pending
    assert handle.id not in runner._futures
    assert not ran

    other = JobRunner(store, max_workers=1, dispatch=True)
    other.register("noop", JobSpec, handler)
    other.dispatch_pending()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = store.get(handle.id)
        if job.status == JobStatus.succeeded:
            break
        time.sleep(0.05)

    other.shutdown(wait=True)
    runner.shutdown(wait=True)

    assert store.get(handle.id).status == JobStatus.succeeded
    assert ran == [True]
