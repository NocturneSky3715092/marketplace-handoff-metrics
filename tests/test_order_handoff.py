from marketplace_metrics import (
    BuyerUpdate,
    SellerAsset,
    decide_handoff,
    handoff_metrics,
)


def test_handoff_waits_for_missing_license_and_buyer_email() -> None:
    decision = decide_handoff(
        (
            SellerAsset("download", True),
            SellerAsset("license", False),
            SellerAsset("receipt", True),
        ),
        (BuyerUpdate("email", False), BuyerUpdate("in_app", True)),
    )

    assert decision.state == "waiting"
    assert decision.missing_assets == ("license",)
    assert decision.pending_updates == 1
    assert [(item.name, item.value, item.type) for item in handoff_metrics("craft", decision)] == [
        ("seller_assets_missing", 1, "gauge"),
        ("buyer_updates_pending", 1, "gauge"),
        ("order_handoff_evaluated", 1, "counter"),
    ]
