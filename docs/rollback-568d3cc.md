# Rollback to 568d3cc

The requested original commit `568d3cc620b7d544717e0677436f898c5b925e93`
became `dd9dcd8aa27b651d61eb6e1c2f35c880b7913e39` when the local account
database was purged from Git history. This rollback is a new commit, not a
rewrite of published history.

Application pages, game logic, startup and dependency versions are restored
to that snapshot, with these deployment/data-safety exceptions:

- Local databases, uploads, editor metadata and secrets remain excluded.
- Migrations 0057–0059, their model definitions and the frozen seed JSON are
  retained. No reverse migrations or production data deletion is performed.
  Calendar UI and newer arcade verification logic are rolled back; the
  additional tables/columns remain compatible with existing deployments.
- The public read-only health endpoints and exact loopback hosts remain so
  an already configured Timeweb health probe does not become a 404/400.
- Startup requires explicit DATABASE_URL and uses unbuffered output. It does
  not run the newly introduced blocking security audit.

This is a recovery snapshot, not a security upgrade: newer dependency and
arcade-verification hardening is rolled back too. Reapply those changes in
small tested releases after confirming the deployment is healthy.

Do not rotate the existing SECRET_KEY or change production database settings
as part of this rollback. A Git push alone does not confirm Timeweb health.

Validation: all 372 backend tests passed on isolated PostgreSQL with the
restored pinned dependencies. A real start.sh boot against a fresh temporary
database completed migrations/static collection and served health, home,
login and registration through Gunicorn (2.1 seconds locally). Public and
loopback Host headers passed; an unrelated domain was rejected. Django system
checks, dependency consistency and migration/model consistency passed.
