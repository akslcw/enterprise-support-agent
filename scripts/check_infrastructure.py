import asyncio
import sys

from psycopg import AsyncConnection
from redis.asyncio import Redis

from app.settings import (
    postgres_connection_string,
    redis_connection_string,
)


async def main() -> None:
    async with await AsyncConnection.connect(
        postgres_connection_string()
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT current_database(), current_user"
            )
            database, user = await cursor.fetchone()

    redis = Redis.from_url(
        redis_connection_string(),
        decode_responses=True,
    )

    try:
        await redis.set(
            "stage08:infrastructure-check",
            "ok",
            ex=10,
        )
        redis_value = await redis.get(
            "stage08:infrastructure-check"
        )
    finally:
        await redis.aclose()

    print(
        "PostgreSQL 连接成功："
        f"database={database}, user={user}"
    )
    print(f"Redis 读写成功：value={redis_value}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())