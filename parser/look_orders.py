from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
from parser.database import SessionLocal

from celery import Celery

from sqlalchemy.future import select

from parser.models import Order, TeamLeed

  

app = Celery(
    "tasks",
    broker="sqla+postgresql://avnadmin:AVNS_WuKZ_IhjhElCEeNK1j6@pg-30cc2364-mark-23c7.l.aivencloud.com:21288/defaultdb",
    backend="db+postgresql://avnadmin:AVNS_WuKZ_IhjhElCEeNK1j6@pg-30cc2364-mark-23c7.l.aivencloud.com:21288/defaultdb",
)
@app.task(name="tasks.distribute_orders_to_team_leaders")
def distribute_orders_to_team_leaders():
    """
    Distribute unassigned orders to team leaders every 5 minutes.
    """
    async def distribute():
        async with SessionLocal() as db:
            try:
                # Fetch unassigned orders
                stmt_unassigned = select(Order).where(Order.team_leader_id.is_(None))
                result_unassigned = await db.execute(stmt_unassigned)
                unassigned_orders = result_unassigned.scalars().all()

                if not unassigned_orders:
                    print("No unassigned orders to distribute.")
                    return

                # Fetch all team leaders
                stmt_team_leaders = select(TeamLeed)  # Correct model name
                result_team_leaders = await db.execute(stmt_team_leaders)
                team_leaders = result_team_leaders.scalars().all()

                if not team_leaders:
                    print("No team leaders available for assignment.")
                    return

                # Assign orders in a round-robin fashion
                team_leader_count = len(team_leaders)
                for i, order in enumerate(unassigned_orders):
                    team_leader = team_leaders[i % team_leader_count]
                    order.team_leader_id = team_leader.id
                    print(f"Assigned Order ID {order.id} to Team Leader ID {team_leader.id}")

                await db.commit()

            except Exception as e:
                print(f"Error during order distribution: {e}")

    import asyncio
    asyncio.run(distribute())


app.conf.beat_schedule = {
    "distribute-orders-to-team-leaders": {
        "task": "tasks.distribute_orders_to_team_leaders",
        "schedule": 2 * 60,  # Every 5 minutes
    },
}
