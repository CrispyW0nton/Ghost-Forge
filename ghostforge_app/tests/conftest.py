"""Per-test isolated Flask app fixtures.

Each test gets its own data root so SQLite job stores, slice plans,
and uploaded files don't leak between tests.
"""

from __future__ import annotations

import pytest

from ghostforge_app.app import create_app


@pytest.fixture()
def app(tmp_path):
    flask_app = create_app(data_root=tmp_path)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def ctx(app):
    return app.config["GHOSTFORGE_CTX"]
