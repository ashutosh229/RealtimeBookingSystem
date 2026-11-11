"""python -m app.worker.runner relay|consumers"""

import asyncio
import logging
import signal
import sys

from app.messaging import consumer, relay
from app.platform import db
from app.worker.handlers import HANDLERS


async def main(role: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    await db.init_pool()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    try:
        if role == "relay":
            await relay.run_relay(stop)
        elif role == "consumers":
            await consumer.run_consumers(stop, handlers=HANDLERS)
        else:
            raise SystemExit(f"unknown role {role!r}: use relay or consumers")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ""))
