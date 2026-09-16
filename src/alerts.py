"""Mattermost alerting for critical indexer failures.

Mirrors asi-chain-faucet's alerts service so both projects post the same shape of
message and are configured with the same environment variables.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

SERVICE_NAME = "asi-indexer"


class AlertKind(Enum):
    """The only events that raise an alert.

    Throttling is keyed on this, so a storm of failures of the same kind
    collapses into a single message.
    """

    NODE_UNREACHABLE = "node_unreachable"
    DATABASE_UNREACHABLE = "database_unreachable"
    SYNC_STALLED = "sync_stalled"
    CHAIN_REORG_DETECTED = "chain_reorg_detected"
    INDEXER_STOPPED = "indexer_stopped"
    BLOCKS_STUCK = "blocks_stuck"
    SYNC_FALLING_BEHIND = "sync_falling_behind"

    def title(self) -> str:
        return _TITLES[self]


_TITLES = {
    AlertKind.NODE_UNREACHABLE: "Node unreachable",
    AlertKind.DATABASE_UNREACHABLE: "Database unreachable",
    AlertKind.SYNC_STALLED: "Sync stalled",
    AlertKind.CHAIN_REORG_DETECTED: "Chain reorg detected",
    AlertKind.INDEXER_STOPPED: "Indexer stopped",
    AlertKind.BLOCKS_STUCK: "Block sync stuck",
    AlertKind.SYNC_FALLING_BEHIND: "Sync falling behind",
}


@dataclass
class AlertEvent:
    """A single alert occurrence. Carries no secret-bearing fields by construction."""

    kind: AlertKind
    error: str
    context: List[Tuple[str, str]] = field(default_factory=list)

    def with_context(self, key: str, value: Any) -> "AlertEvent":
        self.context.append((key, str(value)))
        return self


@dataclass
class _ThrottleState:
    last_sent: float
    suppressed: int = 0


@dataclass(frozen=True)
class _DisabledConfig:
    alerts_enabled: bool = False
    mattermost_webhook_url: Optional[str] = None
    mattermost_channel: Optional[str] = None
    mattermost_username: str = SERVICE_NAME
    alert_throttle_sec: int = 3600
    alert_timeout_sec: int = 5
    alert_environment: str = "unknown"


class AlertService:
    """Posts short, throttled failure notices to a Mattermost incoming webhook."""

    def __init__(self, config):
        self.webhook_url: Optional[str] = config.mattermost_webhook_url or None
        self.enabled: bool = bool(config.alerts_enabled and self.webhook_url)
        self.channel: Optional[str] = config.mattermost_channel or None
        self.username: Optional[str] = config.mattermost_username or None
        self.environment: str = config.alert_environment
        self.throttle_window: float = float(config.alert_throttle_sec)
        self.request_timeout: float = float(config.alert_timeout_sec)

        self._throttle: Dict[AlertKind, _ThrottleState] = {}
        self._lock = asyncio.Lock()
        # asyncio keeps only weak references to tasks, so an in-flight delivery can be
        # garbage collected mid-request unless we hold onto it
        self._pending: Set[asyncio.Task] = set()

        if self.enabled:
            logger.info(
                "Alerting enabled",
                environment=self.environment,
                throttle_sec=int(self.throttle_window),
            )
        else:
            logger.info("Alerting is disabled")

    @classmethod
    def disabled(cls) -> "AlertService":
        """A no-op service, for callers with no alerting configured."""
        return cls(_DisabledConfig())

    def notify(self, event: AlertEvent) -> None:
        """Fire-and-forget: never blocks the caller, never raises.

        Delivery failures are logged and nothing else.
        """
        if not self.enabled:
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Alert dropped, no running event loop", kind=event.kind.value)
            return

        task = asyncio.create_task(self._process(event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def notify_and_wait(self, event: AlertEvent) -> None:
        """Awaitable variant for exit paths, where process teardown would otherwise
        race an in-flight delivery. Bounded by the delivery timeout; never raises.
        """
        if not self.enabled:
            return

        try:
            await asyncio.wait_for(self._process(event), timeout=self.request_timeout)
        except asyncio.TimeoutError:
            logger.warning("Alert delivery timed out", kind=event.kind.value)
        except Exception as e:
            logger.warning("Alert delivery failed", kind=event.kind.value, error=str(e))

    async def _process(self, event: AlertEvent) -> None:
        suppressed = await self._reserve_slot(event.kind)
        if suppressed is None:
            return
        await self._deliver(self._format_message(event, suppressed))

    async def _reserve_slot(self, kind: AlertKind) -> Optional[int]:
        """Returns the number of repeats suppressed since the last delivery, or None
        when this alert falls inside the throttle window.
        """
        async with self._lock:
            now = time.monotonic()
            state = self._throttle.get(kind)

            if state is None:
                self._throttle[kind] = _ThrottleState(last_sent=now)
                return 0

            if now - state.last_sent < self.throttle_window:
                state.suppressed += 1
                return None

            suppressed = state.suppressed
            state.last_sent = now
            state.suppressed = 0
            return suppressed

    def _format_message(self, event: AlertEvent, suppressed: int) -> str:
        lines = [
            f":rotating_light: **[{self.environment}] {SERVICE_NAME} — {event.kind.title()}**",
            f"- error: {event.error}",
        ]
        lines.extend(f"- {key}: {value}" for key, value in event.context)
        if suppressed > 0:
            lines.append(
                f"- suppressed: {suppressed} repeat(s) in the previous "
                f"{int(self.throttle_window)}s window"
            )
        return "\n".join(lines) + "\n"

    def _session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout)
        )

    async def _deliver(self, text: str) -> None:
        payload: Dict[str, str] = {"text": text}
        if self.username:
            payload["username"] = self.username
        if self.channel:
            payload["channel"] = self.channel

        try:
            async with self._session() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status >= 400:
                        logger.warning(
                            "Alert delivery rejected", status=response.status
                        )
        except asyncio.TimeoutError:
            logger.warning("Alert delivery timed out")
        except Exception as e:
            logger.warning("Alert delivery failed", error=str(e))
