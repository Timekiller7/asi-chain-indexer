"""Configuration management for the indexer."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Node Configuration
    node_timeout: int = Field(
        default=30,
        description="HTTP/gRPC request timeout in seconds"
    )

    http_port: int = Field(
        default=40453,
        description="HTTP port for status queries"
    )

    grpc_port: int = Field(
        default=40452,
        description="GRPC port for status queries"
    )

    node_host: str = Field(
        default="localhost",
        description="host port for status queries"
    )

    fault_tolerance_threshold: float = Field(
        default=0.67,
        description="BFT safety threshold for consensus status, mirrors the node's own "
                     "casper.fault-tolerance-threshold (defaults.conf); not exposed via any API, "
                     "so it must be kept in sync with the shard's actual config by hand"
    )

    # Database Configuration
    database_url: str = Field(
        default="postgresql://indexer:indexer_pass@localhost:5432/asichain",
        description="PostgreSQL connection URL"
    )
    database_pool_size: int = Field(
        default=20,
        description="Database connection pool size"
    )
    database_pool_timeout: int = Field(
        default=10,
        description="Database pool timeout in seconds"
    )

    # Sync Configuration
    sync_interval: int = Field(
        default=5,
        description="Seconds between sync cycles"
    )
    delay_before_node: float = Field(
        default=0.02,
        description="small delay to avoid overwhelming the node"
    )
    batch_size: int = Field(
        default=100,
        description="Number of blocks to process per batch"
    )
    start_from_block: int = Field(
        default=0,
        description="Block number to start syncing from"
    )

    # Monitoring
    monitoring_port: int = Field(
        default=9090,
        description="Port for metrics and health endpoints"
    )
    health_check_interval: int = Field(
        default=60,
        description="Health check interval in seconds"
    )

    # Alerts (Mattermost incoming webhook)
    alerts_enabled: bool = Field(
        default=False,
        description="Enable Mattermost alerts (requires MATTERMOST_WEBHOOK_URL)"
    )
    mattermost_webhook_url: Optional[str] = Field(
        default=None,
        description="Mattermost incoming webhook URL (secret, never logged)"
    )
    mattermost_channel: Optional[str] = Field(
        default=None,
        description="Override the webhook's default channel"
    )
    mattermost_username: str = Field(
        default="asi-indexer",
        description="Username alerts are posted under"
    )
    alert_throttle_sec: int = Field(
        default=3600,
        description="Per-alert-kind throttle window in seconds; repeats inside it are "
                    "collapsed into a suppressed count"
    )
    alert_timeout_sec: int = Field(
        default=5,
        description="Timeout in seconds for a single webhook delivery attempt"
    )
    alert_environment: str = Field(
        default="unknown",
        description="Environment label shown in the alert title, e.g. internal-dev or devnet"
    )
    sync_stall_threshold: int = Field(
        default=3,
        description="Consecutive failed sync cycles before the loop is considered stalled"
    )
    lag_alert_blocks: int = Field(
        default=500,
        description="Lag depth (in blocks) that, held for lag_alert_cycles without net "
                    "progress, is treated as falling behind rather than a backlog being "
                    "worked through"
    )
    lag_alert_cycles: int = Field(
        default=60,
        description="Cycles of sustained lag deeper than lag_alert_blocks before alerting"
    )
    lag_recovery_ratio: float = Field(
        default=0.9,
        description="Lag counts as recovering when the recent half of the window is at "
                    "most this fraction of the older half; a smaller value demands "
                    "faster catch-up before the alert is held back"
    )
    cursor_stuck_cycles: int = Field(
        default=3,
        description="Cycles the sync cursor may sit at the same height, retrying a "
                    "failing block, before that stops looking transient"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )

    # Feature Flags
    enable_asi_transfer_extraction: bool = Field(
        default=True,
        description="Enable ASI transfer extraction from deployments"
    )
    enable_pending_deploys_sync: bool = Field(
        default=True,
        description="Enable pending deploys polling from the node's getPendingDeploys RPC"
    )
    enable_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics"
    )
    enable_health_check: bool = Field(
        default=True,
        description="Enable health check endpoint"
    )

    # Hasura Configuration (optional, not used by indexer but may be in env)
    hasura_admin_secret: Optional[str] = Field(
        default=None,
        description="Hasura admin secret (not used by indexer)"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # allow extra fields in .env


# Global settings instance
settings = Settings()
