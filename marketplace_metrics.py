"""Decide whether an order can be handed off and build its metrics."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SellerAsset:
    kind: Literal["download", "license", "receipt"]
    ready: bool


@dataclass(frozen=True)
class BuyerUpdate:
    channel: Literal["email", "in_app"]
    delivered: bool


@dataclass(frozen=True)
class HandoffDecision:
    state: Literal["ready", "waiting"]
    missing_assets: tuple[str, ...]
    pending_updates: int


@dataclass(frozen=True)
class Metric:
    name: str
    value: int
    type: Literal["counter", "gauge"]
    tags: dict[str, str]


def decide_handoff(
    seller_assets: tuple[SellerAsset, ...],
    buyer_updates: tuple[BuyerUpdate, ...],
) -> HandoffDecision:
    """Require the download and license before the seller releases an order."""
    required = {"download", "license"}
    available = {asset.kind for asset in seller_assets if asset.ready}
    missing = tuple(sorted(required - available))
    pending = sum(not update.delivered for update in buyer_updates)
    return HandoffDecision(
        state="ready" if not missing and pending == 0 else "waiting",
        missing_assets=missing,
        pending_updates=pending,
    )


def handoff_metrics(
    marketplace: str,
    decision: HandoffDecision,
) -> tuple[Metric, ...]:
    tags = {"marketplace": marketplace, "handoff_state": decision.state}
    return (
        Metric("seller_assets_missing", len(decision.missing_assets), "gauge", tags),
        Metric("buyer_updates_pending", decision.pending_updates, "gauge", tags),
        Metric("order_handoff_evaluated", 1, "counter", tags),
    )
