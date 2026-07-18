"""Core domain layer — models, naming, and the generation workflow.

Owns everything that is the product rather than an I/O concern:
the service configuration model, document registry, filename rules,
and the orchestration that turns (DayContent, ServiceConfig) into the
five output PDFs. UI adapters (the web server) depend on this package;
it never imports them.
"""

from __future__ import annotations
