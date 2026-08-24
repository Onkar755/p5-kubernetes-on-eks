import asyncio
import os
import random
from typing import Annotated

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.metrics import PrometheusMiddleware, REGISTRY

app = FastAPI()
app.add_middleware(PrometheusMiddleware, router=app.router)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@app.get("/health")
def health():
    return {"status": "healthy"}


def fizzbuzz(number: int) -> int | str:
    if number % 15 == 0:
        return "FizzBuzz"
    if number % 3 == 0:
        return "Fizz"
    if number % 5 == 0:
        return "Buzz"
    return number


class FizzBuzzResponse(BaseModel):
    number: int
    result: int | str


@app.get("/fizzbuzz/{number}", response_model=FizzBuzzResponse)
def fizzbuzz_endpoint(number: int):
    return {"number": number, "result": fizzbuzz(number)}


@app.get("/count")
def count():
    updated_count = redis_client.incr("count")
    return {"count": updated_count}


# --- Chaos: load shaping for the monitoring project -------------------------
#
# Latency is drawn from a lognormal distribution. The parameters are derived
# from two targets: a 40ms median and a 10x p50:p99 spread, so that histogram
# bucket boundaries are a real design decision rather than an arbitrary one.
#
#   median = exp(mu)                  -> mu = ln(0.040) = -3.2189
#   p99    = exp(mu + 2.3263 * sigma) -> sigma = ln(10) / 2.3263 = 0.9898
#
# Resulting quantiles: p50 40.0ms, p90 142.3ms, p99 400.2ms, p99.9 852.5ms.
LATENCY_MU = -3.2189
LATENCY_SIGMA = 0.99

# Safety bounds on the base draw, not shaping knobs. At these values the upper
# clamp fires for 1 draw in ~25,800 and the lower clamp for 1 in ~10,300, so
# neither produces a visible pile-up on a single value in a histogram.
LATENCY_MIN_S = 0.001
LATENCY_MAX_S = 2.0


def _draw_latency(multiplier: float) -> float:
    """Draw a sleep duration in seconds, clamped and then scaled.

    The clamp bounds the base distribution and the multiplier scales the
    clamped value. Clamping after scaling would let a large multiplier
    saturate most requests at the ceiling and flatten the distribution into a
    spike; this way the shape survives and the multiplier stays linear.
    """
    draw = random.lognormvariate(LATENCY_MU, LATENCY_SIGMA)
    return min(max(draw, LATENCY_MIN_S), LATENCY_MAX_S) * multiplier


ErrorRate = Annotated[float, Field(ge=0.0, le=1.0)]
LatencyMultiplier = Annotated[float, Field(gt=0.0)]


class ChaosConfig(BaseModel):
    """Live chaos state, and the response model for /admin/chaos."""

    model_config = ConfigDict(validate_assignment=True)

    error_rate: ErrorRate = 0.0
    latency_multiplier: LatencyMultiplier = 1.0


class ChaosUpdate(BaseModel):
    """Body for PUT /admin/chaos.

    Both fields are required, so PUT is a full replacement: a partial body is
    a 422 rather than a silent reset of the field that was left out.
    """

    error_rate: ErrorRate
    latency_multiplier: LatencyMultiplier


chaos = ChaosConfig()


class ItemResponse(BaseModel):
    item_id: int
    name: str


@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int):
    # Snapshot the config into locals before the first await. With no await
    # between the two reads the event loop cannot switch tasks mid-read, so
    # each request sees a self-consistent config even if a PUT lands midway.
    error_rate = chaos.error_rate
    delay = _draw_latency(chaos.latency_multiplier)

    await asyncio.sleep(delay)

    # Sleep first, then fail: an injected failure pays the full latency cost,
    # the way a real failing request does.
    if random.random() < error_rate:
        raise HTTPException(status_code=500, detail="chaos: injected failure")

    return {"item_id": item_id, "name": f"item-{item_id}"}


@app.get("/admin/chaos", response_model=ChaosConfig)
async def get_chaos():
    return chaos


@app.put("/admin/chaos", response_model=ChaosConfig)
async def put_chaos(update: ChaosUpdate):
    # Mutate the singleton in place rather than rebinding the module global,
    # so anything holding a reference to it sees the update.
    chaos.error_rate = update.error_rate
    chaos.latency_multiplier = update.latency_multiplier

    return chaos

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )