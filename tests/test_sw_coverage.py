"""Verify spend API path is covered by service worker network-first handler."""


def test_sw_handles_spend_api_path():
    """Service worker fetch handler must match /spend/api/ paths with a regex that covers
    /api/*, /spend/api/*, /brain/api/*, etc. without matching non-API paths like /apiary/.

    Note: this is a source-code property test, not a runtime behavioral test.
    Full SW intercept testing requires browser-level E2E tests.
    """
    with open("static/sw.js") as f:
        sw = f.read()
    # The SW should use the word-boundary-safe regex form
    assert r"/(?:^|\/)api\//.test(url.pathname)" in sw, (
        "SW fetch handler must use regex /(?:^|\\/)api\\//.test(url.pathname) "
        "to safely cover /spend/api/ without matching /apiary/."
    )
