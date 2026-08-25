"""Small, in-process async fan-out for server events."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


EventT = TypeVar("EventT")
Subscriber = Callable[[EventT], Awaitable[None]]


class SubscriberLimitExceededError(Exception):
    """A pub/sub instance has reached its subscriber capacity."""

    def __init__(self, max_subscribers: int) -> None:
        self.max_subscribers = max_subscribers
        super().__init__(f"maximum of {max_subscribers} subscribers reached")


class PubSub[EventT]:
    """Fan events out to in-process async subscribers.

    Subscribers are invoked concurrently. A failing subscriber is isolated so
    the publisher and other subscribers can continue receiving events.
    """

    def __init__(self, *, max_subscribers: int = 50) -> None:
        self._max_subscribers = max_subscribers
        self._subscribers: set[Subscriber[EventT]] = set()

    def subscribe(self, subscriber: Subscriber[EventT]) -> None:
        """Register a subscriber, rejecting a new one beyond the configured cap."""
        if subscriber not in self._subscribers:
            if len(self._subscribers) >= self._max_subscribers:
                raise SubscriberLimitExceededError(self._max_subscribers)
            self._subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber[EventT]) -> None:
        """Stop delivering future events to a subscriber."""
        self._subscribers.discard(subscriber)

    async def publish(self, event: EventT) -> None:
        """Deliver an event to the subscribers present at publish time."""
        await asyncio.gather(
            *(self._deliver(subscriber, event) for subscriber in self._subscribers),
        )

    async def _deliver(self, subscriber: Subscriber[EventT], event: EventT) -> None:
        try:
            await subscriber(event)
        except Exception:
            pass
