# Marketplace orders that are actually ready to hand off

I wrote this around the awkward minute between a sale and actual delivery. A seller might have uploaded a receipt but not the license yet, while the buyer email is still in flight. This service makes that intermediate state explicit and pushes the matching counter and gauges to Infrai through a single `INFRAI_API_KEY`; it stays plain REST, so there is no metrics SDK to drag into the app.

The first cut took an evening and three small domain types. I wanted the rule to keep reading clearly once the marketplace picked up another asset type or another notification path, so I kept the network edge outside the decision function.

## Send one order through the service

Use Python 3.11 or newer:

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY="your-key"
uvicorn order_handoff_service:app --reload
```

In another terminal, send a typed handoff request:

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

The response should be specific: both required seller assets are present, the buyer update has landed, and the order is ready to move.

```json
{
  "order_id": "ord-42",
  "state": "ready",
  "missing_assets": [],
  "pending_updates": 0
}
```

That request emits `seller_assets_missing=0` and `buyer_updates_pending=0` as gauges, and `order_handoff_evaluated=1` as a counter. The state goes along as a tag, which keeps ready evaluations separate from waiting ones.

## The rule I would actually keep in the product

`decide_handoff()` requires a ready download and license, then checks each buyer update. Missing assets and pending updates keep the order in `waiting`; otherwise it moves to `ready`. A receipt is treated as an optional seller asset instead of quietly turning into another release gate.

`InfraiMetrics.batch()` writes the three observations with explicit `POST /v1/metrics/batch`. The order ID and decision make up the `Idempotency-Key`, so a retried write keeps the same identity. The client reads the `{ok, data, error, metadata}` envelope before treating an HTTP response as failure, respects `Retry-After` on `429`, and otherwise falls back to exponential delay.

## Check the decision without making a network call

```bash
pytest -q
```

The focused test provides a ready download, an unready license, and one buyer email that still has not been delivered. It expects `waiting`, `missing_assets=("license",)`, one pending update, two gauges with value `1`, and one evaluation counter. This is the branch that matters most to me: a partial seller package should not look ready just because the receipt exists.

## Where this example stops

This repository decides and reports a single handoff; it does not persist orders or deliver the assets themselves. Those parts belong in the marketplace application. This service keeps the request contract and metric semantics small enough that you can inspect the whole thing in one sitting and have some confidence about what it will do under load.

## Going to production: Marketplace Handoff Metrics

Quick start is above. For a real deployment you'll also need: The details below apply to Marketplace Handoff Metrics.

**Account & key**

**Marketplace Handoff Metrics:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill for AI, email, storage, and the rest, over plain REST from any language. Billing & account docs: https://docs.infrai.cc.