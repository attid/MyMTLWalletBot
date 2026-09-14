import pytest

from other.web_tools import _sanitize_decode_html, _escape_scval_tags


# Fragment taken from a real eurmtl.me/remote/decode response for a
# multi-sign update transaction (GCVT...GORA, 15 SetOptions operations).
REAL_DECODE_FRAGMENT = (
    "Sequence Number 233839245322616848 (свободно 4022.4989505 XLM)<br>"
    "Fee 227272725<br><span >MaxTime ! 15.09.2026 22:31:45 UTC</span><br>"
    "Операции с аккаунта "
    '<a href="https://viewer.eurmtl.me/account/GCVTXUMIUAENJH2XY4AOVGTJKPSCOXW3746PUH7QFGPBDOPPHYLIGORA" '
    'target="_blank">GCVT..GORA</a><br>'
    "&nbsp;&nbsp;No memo<br><br>"
    "&nbsp;&nbsp;&nbsp;&nbsp;Изменяем подписанта "
    '<a href="https://viewer.eurmtl.me/account/GAATY6RRLYL4CB6SCSUSSEELPTOZONJZ5WQRZQKSIWFKB4EXCFK4BDAM" '
    'target="_blank">GAAT..BDAM</a> новые голоса : 0<br>'
    '<div style="color: orange;">Номер Sequence больше на 17385928829960166</div><br>'
    "Данные <scString>value</scString> конец"
)


@pytest.fixture
def sanitized_real() -> str:
    return _sanitize_decode_html(_escape_scval_tags(REAL_DECODE_FRAGMENT))


def test_no_telegram_forbidden_tags(sanitized_real):
    assert "target=" not in sanitized_real
    assert "<span" not in sanitized_real
    assert "<div" not in sanitized_real
    assert "<br" not in sanitized_real


def test_span_warning_kept_and_bold(sanitized_real):
    assert "<b>MaxTime ! 15.09.2026 22:31:45 UTC</b>" in sanitized_real


def test_div_warning_kept_and_bold(sanitized_real):
    assert "<b>Номер Sequence больше на 17385928829960166</b>" in sanitized_real


def test_links_keep_only_href(sanitized_real):
    assert '<a href="https://viewer.eurmtl.me/account/GCVTXUMIUAENJH2XY4AOVGTJKPSCOXW3746PUH7QFGPBDOPPHYLIGORA">' in sanitized_real
    assert ">GCVT..GORA</a>" in sanitized_real


def test_line_breaks_and_nbsp(sanitized_real):
    assert "\n" in sanitized_real
    assert "&nbsp;" not in sanitized_real
    assert "No memo" in sanitized_real


def test_scval_tags_escaped_as_text(sanitized_real):
    assert "<scString>" not in sanitized_real
    assert "&lt;scString&gt;value&lt;/scString&gt;" in sanitized_real
    assert "Данные value конец" not in sanitized_real  # tags escaped, not stripped


def test_plain_telegram_tags_untouched():
    src = "<b>bold</b> <i>it</i> <u>u</u> <s>s</s> <code>c</code> <a href=\"https://x.example\">l</a>"
    assert _sanitize_decode_html(src) == src


def test_unknown_tags_stripped_content_kept():
    src = "<table><tr><td>row data</td></tr></table>"
    assert _sanitize_decode_html(src) == "row data"


def test_link_without_href_dropped_but_text_kept():
    src = 'see <a name="x">this</a> now'
    assert _sanitize_decode_html(src) == "see this now"


def test_br_variants():
    assert _sanitize_decode_html("a<br>b<br/>c<br />d") == "a\nb\nc\nd"
