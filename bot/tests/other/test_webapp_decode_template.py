from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DECODE_TEMPLATE = PROJECT_ROOT / "webapp" / "templates" / "decode.html"
I18N_SCRIPT = PROJECT_ROOT / "webapp" / "static" / "js" / "i18n.js"


def test_decode_template_renders_complete_path_payment_details() -> None:
    template = DECODE_TEMPLATE.read_text(encoding="utf-8")

    for field in (
        "operation.sendAsset",
        "operation.sendAmount",
        "operation.sendMax",
        "operation.destAsset",
        "operation.destMin",
        "operation.destAmount",
        "operation.path",
    ):
        assert field in template

    assert "function formatPaymentPath(operation)" in template
    assert (
        "[operation.sendAsset, ...(operation.path || []), operation.destAsset]"
        in template
    )


def test_decode_path_payment_labels_exist_in_russian_and_english() -> None:
    i18n = I18N_SCRIPT.read_text(encoding="utf-8")

    for key in (
        "decode.send_asset",
        "decode.send_amount",
        "decode.send_max",
        "decode.destination_asset",
        "decode.destination_min",
        "decode.destination_amount",
        "decode.path",
    ):
        assert i18n.count(f'"{key}"') == 2
