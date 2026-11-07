from __future__ import annotations
import asyncio
from collections import defaultdict

class Bus:
    """Pub/sub asyncio. In caso di saturazione scarta l'evento più vecchio:
    nei mercati in tempo reale un dato fresco vale più di una coda perfetta."""
    def __init__(self, maxsize: int = 50_000):
        self.maxsize = maxsize
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.counts: dict[str, int] = defaultdict(int)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        self._subs[topic].append(q)
        return q

    def publish(self, topic: str, event) -> None:
        self.counts[topic] += 1
        for q in list(self._subs.get(topic, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(event)
                except Exception:
                    pass

    def stats(self):
        return dict(self.counts)
