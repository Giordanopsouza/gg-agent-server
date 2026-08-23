from __future__ import annotations

import asyncio

import pytest

from gg.server.pubsub import PubSub, SubscriberLimitExceededError


@pytest.mark.anyio
async def test_publish_delivers_to_all_current_subscribers() -> None:
    received_by_first: list[str] = []
    received_by_second: list[str] = []
    pubsub: PubSub[str] = PubSub()

    async def first(event: str) -> None:
        received_by_first.append(event)

    async def second(event: str) -> None:
        received_by_second.append(event)

    pubsub.subscribe(first)
    pubsub.subscribe(second)

    await pubsub.publish("hello")

    assert received_by_first == ["hello"]
    assert received_by_second == ["hello"]


@pytest.mark.anyio
async def test_unsubscribe_stops_future_deliveries() -> None:
    received: list[str] = []
    pubsub: PubSub[str] = PubSub()

    async def subscriber(event: str) -> None:
        received.append(event)

    pubsub.subscribe(subscriber)
    await pubsub.publish("first")
    pubsub.unsubscribe(subscriber)
    await pubsub.publish("second")

    assert received == ["first"]


@pytest.mark.anyio
async def test_failing_subscriber_does_not_block_others() -> None:
    received: list[str] = []
    pubsub: PubSub[str] = PubSub()

    async def failing_subscriber(event: str) -> None:
        raise RuntimeError(event)

    async def healthy_subscriber(event: str) -> None:
        await asyncio.sleep(0)
        received.append(event)

    pubsub.subscribe(failing_subscriber)
    pubsub.subscribe(healthy_subscriber)

    await pubsub.publish("still delivered")

    assert received == ["still delivered"]


def test_subscriber_cap_rejects_the_51st_subscriber() -> None:
    pubsub: PubSub[int] = PubSub()

    async def subscriber(event: int) -> None:
        del event

    subscribers = [
        (lambda event, index=index: subscriber(event)) for index in range(50)
    ]
    for callback in subscribers:
        pubsub.subscribe(callback)

    async def fifty_first(event: int) -> None:
        del event

    with pytest.raises(SubscriberLimitExceededError, match="maximum of 50"):
        pubsub.subscribe(fifty_first)
