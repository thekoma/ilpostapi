import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional


class RateLimiter:
    def __init__(self, requests_per_minute: int = 30):
        self.rate = requests_per_minute
        self.tokens = requests_per_minute
        self.last_update = datetime.utcnow()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = datetime.utcnow()
            time_passed = (now - self.last_update).total_seconds() / 60.0
            self.tokens = min(self.rate, self.tokens + time_passed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    async def wait(self):
        while not await self.acquire():
            await asyncio.sleep(60 / self.rate)  # Wait for approximately one token

    async def __aenter__(self):
        await self.wait()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass  # Non abbiamo bisogno di fare nulla all'uscita


class GlobalRateLimiter:
    def __init__(self, rate_limit_ms: int = 20):
        self.rate_limit_ms = rate_limit_ms
        self.last_call: float = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        """Attende il tempo necessario per rispettare il rate limit."""
        async with self._lock:
            current_time = time.time() * 1000  # Converti in millisecondi
            time_since_last_call = current_time - self.last_call

            if time_since_last_call < self.rate_limit_ms:
                wait_time = (
                    self.rate_limit_ms - time_since_last_call
                ) / 1000  # Converti in secondi
                await asyncio.sleep(wait_time)

            self.last_call = time.time() * 1000


# Istanza globale del rate limiter per le chiamate API
api_rate_limiter = GlobalRateLimiter(rate_limit_ms=100)

# Istanza globale del rate limiter per il rate limiting generale
rate_limiter = RateLimiter()
