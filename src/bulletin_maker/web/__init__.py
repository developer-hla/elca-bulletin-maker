"""Web adapter — FastAPI server exposing the core over HTTP.

Serves the wizard SPA and a JSON API. Runs locally (bulletin-maker
opens a browser at localhost) and unchanged in a container for hosted
deployments.
"""

from __future__ import annotations
