"""Back-office admin (SQLAdmin) — a *delivery layer*, not a bounded context.

Architectural dependency rule for this package:

- ``app.admin`` MAY import modules' infrastructure (persistence models,
  repositories) and core services. This mirrors how Django admin sits on
  top of the ORM: the admin is an operations tool that reads/writes
  persistence models directly.
- Nothing outside ``app.admin`` may import from ``app.admin``. Routers,
  use cases, domain code, and core must never depend on the admin. This
  keeps the admin removable without touching any module.
- Admin writes intentionally bypass use cases and the event bus (same
  trade-off as Django admin). Domain workflows belong to the API; the
  admin is for ops fixes only.

The admin is attached to the application in ``app.main`` via
``app.admin.setup.create_admin(app)``.
"""
