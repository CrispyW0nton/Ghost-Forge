from __future__ import annotations

import time

from ghostforge_core.jobs import JobRunner, JobStore
from ghostforge_core.types import JobSpec, JobStatus


def test_job_cancel_observed_within_one_second(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite")
    runner = JobRunner(store, max_workers=1)
    observed_at: list[float] = []

    def long_running(spec, reporter, cancel):
        start = time.monotonic()
        while True:
            if cancel.is_cancel_requested():
                observed_at.append(time.monotonic() - start)
                cancel.throw_if_cancelled()
            time.sleep(0.05)

    runner.register("slow", JobSpec, long_running)
    handle = runner.submit("slow", JobSpec(prompt="cancel me"))
    time.sleep(0.1)
    store.request_cancel(handle.id)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = store.get(handle.id)
        if job.status == JobStatus.cancelled:
            break
        time.sleep(0.05)

    runner.shutdown(wait=True)

    job = store.get(handle.id)
    assert job.status == JobStatus.cancelled
    assert observed_at
    assert observed_at[0] < 1.0
