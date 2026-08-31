"""One-off: overwrite the stored Campaign.stats JSON counters with values
recomputed from the messages/coupons tables.

Since campaign_stats_service now derives these on every read, the stored
JSON is no longer authoritative — but leaving drifted values in the DB is
confusing for anyone inspecting rows directly. This resyncs them.

    python -m scripts.reconcile_campaign_stats           # dry run
    python -m scripts.reconcile_campaign_stats --apply   # write

Run from backend/ with the target DATABASE_URL in the environment.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.services.campaign_stats_service import compute_campaign_stats  # noqa: E402


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        campaigns = (await db.execute(select(Campaign))).scalars().all()
        derived = await compute_campaign_stats(db, [c.id for c in campaigns])

        changed = 0
        for c in campaigns:
            d = derived.get(c.id, {})
            new_stats = dict(c.stats or {})
            before = dict(new_stats)
            for k in ("sent", "delivered", "read", "failed", "queued", "coupons_redeemed"):
                new_stats[k] = d.get(k, 0)
            if new_stats != before:
                changed += 1
                print(f"{c.name!r} ({c.id})")
                print(f"   before: {before}")
                print(f"   after : {new_stats}")
                if apply:
                    c.stats = new_stats

        if apply and changed:
            await db.commit()
            print(f"\n✅ Updated {changed} campaign(s).")
        else:
            print(f"\n{changed} campaign(s) would change. Re-run with --apply to write.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
