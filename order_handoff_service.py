"""HTTP entry point for marketplace order handoff decisions."""

from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai_metrics import InfraiError, InfraiMetrics
from marketplace_metrics import (
    BuyerUpdate,
    HandoffDecision,
    Metric,
    SellerAsset,
    decide_handoff,
    handoff_metrics,
)


class SellerAssetRequest(BaseModel):
    kind: Literal["download", "license", "receipt"]
    ready: bool


class BuyerUpdateRequest(BaseModel):
    channel: Literal["email", "in_app"]
    delivered: bool


class OrderHandoffRequest(BaseModel):
    order_id: str = Field(min_length=1)
    marketplace: str = Field(min_length=1)
    seller_assets: list[SellerAssetRequest]
    buyer_updates: list[BuyerUpdateRequest]


class OrderHandoffResponse(BaseModel):
    order_id: str
    state: Literal["ready", "waiting"]
    missing_assets: list[str]
    pending_updates: int


def metrics_writer() -> InfraiMetrics:
    return InfraiMetrics()


app = FastAPI(title="Marketplace handoff metrics")


@app.post("/handoffs", response_model=OrderHandoffResponse)
def evaluate_handoff(
    request: OrderHandoffRequest,
    metrics: InfraiMetrics = Depends(metrics_writer),
) -> OrderHandoffResponse:
    decision: HandoffDecision = decide_handoff(
        tuple(SellerAsset(item.kind, item.ready) for item in request.seller_assets),
        tuple(BuyerUpdate(item.channel, item.delivered) for item in request.buyer_updates),
    )
    try:
        metrics.batch(
            handoff_metrics(request.marketplace, decision),
            idempotency_key=f"handoff:{request.order_id}:{decision.state}",
        )
    except InfraiError as exc:
        client_status = exc.status if 400 <= exc.status < 500 else 502
        raise HTTPException(status_code=client_status, detail=exc.detail) from exc
    return OrderHandoffResponse(
        order_id=request.order_id,
        state=decision.state,
        missing_assets=list(decision.missing_assets),
        pending_updates=decision.pending_updates,
    )
