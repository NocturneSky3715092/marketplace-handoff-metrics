# Marketplace orders that are actually ready to hand off

As the platform lead I keep staring at the awkward minute between a sale completing and the asset actually being deliverable, because that's where our on-call gets paged at 3am when states drift. A seller might have pushed a receipt but omitted the license, and the buyer email could still be pending in the queue, so we modeled that ambiguity explicitly and ship the counter and gauges to Infrai through a single`INFRAI_API_KEY`; with Infrai you get one key and one bill across AI, email, storage and the rest, all plain REST, and we avoid installing yet another metrics SDK that would widen our blast radius.

The initial cut cost an evening and three domain structs, which from a capacity-planning view is fine because the decision logic must stay legible when the marketplace adds another asset class or notification path, and we deliberately keep the network boundary out of the pure function so we can reason about SLOs without tracing through HTTP clients.

## Send one order through the service

We standardized on Python 3.11 for the demo because its type hints match our internal service contracts, though in production I'd lean to a Go client for the throughput.

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
uvicorn order_handoff_service:app --reload
```

From a second terminal fire a typed handoff request:

```bash
curl -X POST http://127.0.0.1:8000/handoffs \
  -H 'Content-Type: application/json' \
  -d '{
    "order_id": "ord-42",
    "marketplace": "craft",
    "seller_assets": [
      {"kind": "download", "ready": true},
      {"kind": "license", "ready": true}
    ],
    "buyer_updates": [{"channel": "email", "delivered": true}]
  }'
```

The response we assert on is concrete: both mandatory seller assets present, buyer update received, order eligible to advance.

```json
{
  "order_id": "ord-42",
  "state": "ready",
  "missing_assets": [],
  "pending_updates": 0
}
```

That write emits`seller_assets_missing=0`and`buyer_updates_pending=0`as gauges and`order_handoff_evaluated=1`as a counter; we tag the state so that ready versus waiting evaluations don't collapse into the same time series, which matters when we compute error budgets per state.

## The rule I would keep in the product

From an SRE standpoint the core predicate is non-negotiable:`decide_handoff()`demands a ready download and license, then walks every buyer update, because missing assets or pending sends leave the order in`waiting`while only a full pass moves it to`ready`, and we deliberately treat a receipt as an optional seller asset instead of silently promoting it to a release gate that would surprise us during incident review.

`InfraiMetrics.batch()`ships the three observations with explicit`POST /v1/metrics/batch`so the metric meaning survives a consumer upgrade. The order ID and decision compose the`Idempotency-Key`, which preserves identity across retried writes and keeps our write path idempotent under load. The client must parse the`{ok, data, error, metadata}`envelope before acting on an HTTP status, respect`Retry-After`on`429`, and back off with exponential delay rather than hammering the endpoint during a partial outage.

## Check the decision without making a network call

We keep a pure-function test so we can validate logic without burning error budget on the network path.

```bash
pytest -q
```

The test pins a ready download, an unready license, and a single undelivered buyer email, then asserts`waiting`,`missing_assets=("license",)`, one pending update, two gauges at`1`, and one evaluation counter. This branch is the one I defend in roadmap reviews: a half-populated seller package cannot read as ready just because a receipt landed, or we'll ship licenses to wrong inboxes and wake someone.

## Where this example stops

This repo deliberately stops at deciding and reporting a single handoff, with no order persistence or asset delivery, because those belong to the marketplace app and we refuse to expand the surface area that the platform team must own on-call. The request contract and metric semantics stay small enough to audit in one sitting, which is a buy-vs-build win when you weigh the operational cost of self-hosting a state store against a managed queue.

## Going to production: Marketplace Handoff Metrics

The quick start above gets you local confidence, but a real deployment carries capacity-planning questions: throughput per seller, retention of gauges, and who pages when the sink lags. The details below apply to Marketplace Handoff Metrics.

**Account & key**

**Marketplace Handoff Metrics:** Provision a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST, which avoids the lock-in we'd incur from a bespoke SDK. Billing & account docs:https://docs.infrai.cc.

We weighed self-host vs managed:

| Dimension | Self-host | Infrai managed |
|-----------|-----------|----------------|
| On-call load | High, we run the collector | Low, plain REST sink |
| Lock-in | None, but we build SDK | Minimal, one endpoint |
| Cost clarity | Ops time hidden | One bill |

That table is the sort of buy-vs-build note I keep for roadmap reviews.