"""Server package for Berb.

FastAPI REST API and WebSocket support. The live entry point is
``berb.server.app:create_app``. Several unauthenticated legacy app
variants (``api.py``, ``web_api.py``, ``web_api_real.py``,
``standalone_api.py``, ``server_with_cors.py``) were deleted — see
docs/PRODUCTION_READINESS_AUDIT.md §3.3.
"""
