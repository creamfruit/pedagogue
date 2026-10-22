from pathlib import Path


def test_every_in_app_purchase_setting_is_documented_and_in_the_blueprint():
    import yaml

    root = Path(__file__).resolve().parents[2]
    deploy = (root / "DEPLOY.md").read_text(encoding="utf-8")
    example = (root / "backend" / ".env.example").read_text(encoding="utf-8")
    frontend_example = (root / "frontend" / ".env.example").read_text(encoding="utf-8")
    blueprint = yaml.safe_load((root / "render.yaml").read_text(encoding="utf-8"))
    api = next(service for service in blueprint["services"] if service["name"] == "pedagogue-api")
    declared = {item["key"] for item in api["envVars"]}
    for name in ("REVENUECAT_WEBHOOK_SECRET", "REVENUECAT_ENTITLEMENT_ID"):
        assert f"`{name}`" in deploy, name
        assert f"{name}=" in example, name
        assert name in declared, name
    for name in ("VITE_REVENUECAT_IOS_API_KEY", "VITE_REVENUECAT_ANDROID_API_KEY"):
        assert f"`{name}`" in deploy, name
        assert f"{name}=" in frontend_example, name
    assert "IAP_SETUP.md" in deploy


def test_the_setup_guide_names_the_product_ids_the_webhook_expects():
    root = Path(__file__).resolve().parents[2]
    guide = (root / "IAP_SETUP.md").read_text(encoding="utf-8")
    for name in ("pedagogue_pro_monthly", "pedagogue_pro_yearly", "REVENUECAT_WEBHOOK_SECRET", "/api/v1/billing/revenuecat/webhook"):
        assert name in guide, name
