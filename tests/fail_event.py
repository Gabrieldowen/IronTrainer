import asyncio
from app.db.session import init_db_pool, close_db_pool
from app.db.repositories.strava_events_repository import insert_event

async def make_test_event():
    pool = await init_db_pool()
    event_id = await insert_event(
        pool,
        object_type="activity",
        aspect_type="update",
        object_id=1,  # won't exist on Strava — fetch will 404 and fail
        owner_id=999999999,  # no connected user
        raw_payload={"test": True},
    )
    print("Created test event id:", event_id)
    await close_db_pool()

asyncio.run(make_test_event())