import asyncio
import logging
import signal

from app.platform import db
from app.platform.config import get_settings
from app.worker import sweeper

log = logging.getLogger("rtbs.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    await db.init_pool()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)  # graceful: finish the current cycle, then exit
        except NotImplementedError:  # Windows
            pass
    interval = get_settings().sweep_interval_seconds
    log.info("worker started, sweep every %ss", interval)
    try:
        while not stop.is_set():
            try:
                async with db.get_pool().acquire() as conn:
                    result = await sweeper.run_locked(conn)
                if result and any(result.values()):
                    log.info("cycle: %s", result)
            except Exception:
                log.exception("sweep cycle failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass
    finally:
        await db.close_pool()
        log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
