import inspect

from gateway.platforms.napcat import NapCatAdapter


def test_connect_accepts_reconnect_flag():
    parameter = inspect.signature(NapCatAdapter.connect).parameters["is_reconnect"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is False
