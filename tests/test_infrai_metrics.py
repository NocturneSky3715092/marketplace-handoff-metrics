import json
from unittest.mock import patch

from infrai_metrics import InfraiMetrics
from marketplace_metrics import Metric


def test_batch_uses_discovery_request_fields() -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"ok": true, "data": {}}'

    with patch("infrai_metrics.urlopen", return_value=Response()) as urlopen:
        InfraiMetrics(api_key="test-key").batch(
            (Metric("orders", 1, "counter", {"marketplace": "craft"}),),
            "handoff:test:ready",
        )

    body = json.loads(urlopen.call_args.args[0].data)
    assert set(body) == {"points", "idempotency_key"}
    assert body["idempotency_key"] == "handoff:test:ready"
    assert body["points"] == [
        {"name": "orders", "value": 1, "type": "counter", "tags": {"marketplace": "craft"}}
    ]
