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


def test_the_model_cache_is_where_huggingface_hub_puts_it():
    """Same folder as the library for each variable it reads: otherwise level 1 is not taken offline, and "Erase
    everything" leaves the models on the disk (XDG_CACHE_HOME set, for instance)."""
    import subprocess
    import sys

    code = ("from geonesclick.paths import hf_hub_cache; import huggingface_hub.constants as c; "
            "print(hf_hub_cache() == __import__('pathlib').Path(c.HF_HUB_CACHE))")
    names = ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME")
    cases = [{}, {"XDG_CACHE_HOME": "/x/cache"}, {"HF_HOME": "~/hf", "XDG_CACHE_HOME": "/x/cache"},
             {"HUGGINGFACE_HUB_CACHE": "/legacy"}, {"HF_HUB_CACHE": "/new", "HUGGINGFACE_HUB_CACHE": "/legacy"}]
    for case in cases:
        env = {k: v for k, v in __import__("os").environ.items() if k not in names} | case
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "True", case
