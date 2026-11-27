import asyncio
import logging
import signal
import time

from app.admin import invariants
from app.availability import cache as availability_cache
from app.platform import db
from app.platform.config import get_settings
from app.worker import sweeper

log = logging.getLogger("rtbs.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    await db.init_pool()
    await availability_cache.init()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)  # graceful: finish the current cycle, then exit
        except NotImplementedError:  # Windows
            pass
    settings = get_settings()
    interval, check_every = settings.sweep_interval_seconds, settings.invariant_check_seconds
    last_check = 0.0
    log.info("worker started, sweep every %ss, invariant check every %ss", interval, check_every)
    try:
        while not stop.is_set():
            try:
                async with db.get_pool().acquire() as conn:
                    result = await sweeper.run_locked(conn)
                if result and any(result.values()):
                    log.info("cycle: %s", result)
                if check_every > 0 and time.monotonic() - last_check >= check_every:
                    last_check = time.monotonic()
                    async with db.get_pool().acquire() as conn:
                        await invariants.run_and_log(conn)
            except Exception:
                log.exception("sweep cycle failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass
    finally:
        await availability_cache.close()
        await db.close_pool()
        log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
