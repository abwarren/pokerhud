"""webapp — merged pokerhud Flask application (dashboard + remote control + equity).

create_app() factory: ONE Flask instance, ONE CORS, ONE Limiter, ONE static dir.
Blueprints register with no url_prefix so every route path is preserved.
"""

from __future__ import annotations

from flask import Flask, request
from flask_cors import CORS

from webapp.remote_bp import limiter


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)  # static served via explicit routes
    CORS(app)

    # Chrome Private Network Access — required for extension/browser fetches to
    # the local API from public poker-site origins.
    @app.after_request
    def _add_private_network_access(response):
        if request.headers.get("Access-Control-Request-Private-Network"):
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    limiter.init_app(app)

    from webapp.dashboard_bp import dashboard_bp
    from webapp.equity_bp import equity_bp
    from webapp.remote_bp import remote_bp
    from webapp.selector_registry import load_profiles, registry_status

    # Slice 4c — selector registry: fail-fast validation at startup (non-fatal:
    # dashboard/equity must never be held hostage by extension profile edits).
    try:
        load_profiles()
        app.logger.info("[SELECTORS] profiles valid: evenbet.json, betconstruct.json")
    except Exception as e:  # SelectorRegistryError
        app.logger.critical(f"[SELECTORS] registry error: {e}")

    @app.get("/api/selectors/status")
    def selectors_status():
        return registry_status()

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(equity_bp)
    app.register_blueprint(remote_bp)
    return app
