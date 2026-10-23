# Jury veto cancellation and vote changes

Staff can open `/paddock-jury/`, select an event, then use **Отменить исключение на этом этапе**. The POST form has CSRF protection and a confirmation describing score/duel recalculation. Cancellation applies to that event only, stops its voting and prevents a jury veto while retaining every ballot. The administrator and timestamp are stored on Event. Repeated cancellation is idempotent. The actual production event is selected by the administrator; this implementation does not cancel a particular live event automatically.

If the event has published/stored scores, cancellation creates a new score revision through the existing publisher, recalculating prediction points, Va-bank and settled duels together. The operation locks Event and is atomic: a failed recalculation rolls back the cancellation as well. It does not approve predictions or remove the separate wheel's Crazy Block. If the event has no published scores, no scores are published prematurely.

The admin audit and event results explicitly distinguish cancellation from a tie. Live Paddock replaces the exclusion announcement with the cancellation notice. Profile/scoring veto checks use the same cancellation-aware helper.

Players may change their target while voting is open. The existing event/voter ballot is updated under the same event lock; there is still exactly one counted ballot per player per event. `created_at` retains its original value, while nullable `updated_at` records the latest change. Legacy votes fall back to their original timestamp in the admin audit. Self-voting, inactive/staff voting, invalid targets and voting after closure remain forbidden. Existing voting-window policy is unchanged.

Migration: `0039_crazy_jury_cancellation_and_revote` adds two nullable Event audit fields and one nullable vote timestamp. No existing votes are deleted or modified by the migration.

Changes: `league/models.py`, `league/crazy_jury.py`, new `league/jury_admin.py`, `league/urls.py`, `league/services.py`, the home/jury-admin/event-detail templates, migration 0039, `league/test_crazy_jury.py` and new `league/test_crazy_jury_controls.py`.

Validation: 17 jury tests pass both against an isolated HEAD-based build and the existing working copy (which has other pending changes). Together with the 15 arcade-library tests, 32 focused tests pass. Coverage includes revoting/one-ballot count, closed/invalid/self votes, staff POST/CSRF protection, cancellation scope, retained votes/audit, score and duel recalculation, idempotent revisions, rollback on publisher error, unapproved predictions, wheel block preservation and Live Paddock text. Migration state and static collection are checked in the isolated build, without migrating the workspace database.

A broader 70-test run had seven failures and three errors in pre-existing duel-message and older arcade/trophy tests. Running the original 61-test baseline without this feature reproduced the same seven failures and three errors. Those unrelated issues were not changed here. Pending working-tree changes to arcade management and the voting-window policy are preserved and excluded from this feature's commit.
