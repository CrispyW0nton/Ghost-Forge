"""Flask application factory.

Composes the legacy v1 blueprint (`ghostforge_app.legacy`) and the new
v2 blueprint (`ghostforge_app.v2`) on top of a shared core context so
the existing Electron UI keeps running unmodified while the rebuilt
React panels can target the v2 surface for new functionality (workers,
KB, audit, engines, slices, GPU runtime).
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.tenancy import TenantRegistry

from .legacy import create_blueprint as create_legacy_bp
from .v2 import create_blueprint as create_v2_bp

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
MAX_UPLOAD = 300 * 1024 * 1024

try:
    from flask_cors import CORS
except ImportError:
    def CORS(*_args, **_kwargs):
        return None


def create_app(
    *,
    data_root: Path | None = None,
    multi_tenant: bool = False,
) -> Flask:
    """Build the Flask app.

    ``multi_tenant=True`` enables tenant isolation: requests must
    carry an ``X-Ghostforge-Tenant`` header (or set
    ``GHOSTFORGE_TENANT`` in the environment) and each tenant gets
    its own ``CoreContext`` rooted at
    ``<data_root>/tenants/<tenant_id>/``. The default tenant
    (``"default"``) keeps using ``data_root`` so single-user
    deployments keep working unchanged.
    """

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
    CORS(app, origins="*", allow_headers=["Content-Type", "Authorization"])

    base_data_root = data_root or BASE_DIR / "data"

    if multi_tenant:
        tenants = TenantRegistry(
            base_config=CoreConfig(data_root=base_data_root),
            context_factory=bootstrap,
        )
        app.config["GHOSTFORGE_TENANTS"] = tenants
        # Eagerly materialise the default tenant so probe / status
        # endpoints have something to talk to before any other
        # request arrives.
        app.config["GHOSTFORGE_CTX"] = tenants.resolve(None)
    else:
        ctx = bootstrap(CoreConfig(data_root=base_data_root))
        app.config["GHOSTFORGE_CTX"] = ctx

    @app.route("/")
    def index():
        return send_from_directory(str(TEMPLATES_DIR), "index.html")

    app.register_blueprint(create_legacy_bp())
    app.register_blueprint(create_v2_bp())
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
