from django.db import migrations
from django.db.models import Q, Sum


def refund_las_vegas_shop(apps, schema_editor):
    db = schema_editor.connection.alias
    Event = apps.get_model("league", "Event")
    CalendarRound = apps.get_model("league", "RaceCalendarRound")
    Competition = apps.get_model("league", "ArcadeCompetition")
    Wallet = apps.get_model("league", "VegasWallet")
    Purchase = apps.get_model("league", "VegasPurchase")

    linked_events = CalendarRound.objects.using(db).filter(
        season_year=2026, circuit="las-vegas",
    ).values("prediction_event_id")
    events = list(Event.objects.using(db).select_for_update().filter(season_year=2026).filter(
        Q(circuit="las-vegas") | Q(pk__in=linked_events)
        | (Q(circuit="") & (Q(name__icontains="Вегас") | Q(name__icontains="Vegas"))),
    ).order_by("pk").values_list("pk", flat=True))
    # Same lock order as the shop. New purchases can proceed once this
    # transaction commits, using the restored balances and empty inventory.
    contests = list(Competition.objects.using(db).select_for_update().filter(
        event_id__in=events, game_key="vegas",
    ).order_by("pk").values_list("pk", flat=True))
    wallet_ids = Purchase.objects.using(db).filter(
        wallet__competition_id__in=contests,
    ).values("wallet_id")
    wallets = Wallet.objects.using(db).select_for_update().filter(
        pk__in=wallet_ids,
    ).order_by("pk")
    count = total = 0
    for wallet in wallets:
        purchases = Purchase.objects.using(db).filter(wallet_id=wallet.pk)
        amount = purchases.aggregate(total=Sum("cost"))["total"]
        if amount is None:
            continue
        wallet.balance += amount
        wallet.revision += 1
        if wallet.last_payload:
            wallet.last_payload["state"] = {
                **wallet.last_payload.get("state", {}),
                "balance": wallet.balance,
                "revision": wallet.revision,
            }
        wallet.save(using=db, update_fields=["balance", "revision", "last_payload"])
        deleted, _ = purchases.delete()
        count += deleted
        total += amount
    if contests:
        print(f"Vegas shop refund (Las Vegas 2026): {count} purchases, {total} cents refunded.")


class Migration(migrations.Migration):
    dependencies = [("league", "0073_daily_grant_2000")]
    operations = [migrations.RunPython(refund_las_vegas_shop)]
