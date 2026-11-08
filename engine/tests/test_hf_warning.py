import logging

from geonesclick.paths import quiet_token_nag

HF_HTTP = "huggingface_hub.utils._http"  # where huggingface_hub logs the X-HF-Warning headers sent by the Hub


def test_token_nag_from_the_hub_is_hidden_other_warnings_are_kept(caplog):
    quiet_token_nag()
    quiet_token_nag()  # called by both entry points: installing the filter twice changes nothing
    log = logging.getLogger(HF_HTTP)
    with caplog.at_level(logging.WARNING, logger=HF_HTTP):
        log.warning("Warning: You are sending unauthenticated requests to the HF Hub. "
                    "Please set a HF_TOKEN to enable higher rate limits and faster downloads.")
        log.warning("This revision is deprecated")
        log.warning("The HF_TOKEN you provided is invalid")
    assert [r.getMessage() for r in caplog.records] == ["This revision is deprecated",
                                                        "The HF_TOKEN you provided is invalid"]
    assert len(log.filters) == 1
