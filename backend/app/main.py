from fastapi import FastAPI

app = FastAPI(title="RealTime Booking System", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    # TODO: check DB connectivity and migration head
    return {"status": "ready"}
