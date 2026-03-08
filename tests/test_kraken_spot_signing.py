from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector


def test_kraken_spot_signing_deterministic():
    sig1 = KrakenSpotConnector.sign_payload(
        api_path="/0/private/Balance",
        nonce="1616492376594",
        payload="nonce=1616492376594",
        api_secret_b64="c2VjcmV0",
    )
    sig2 = KrakenSpotConnector.sign_payload(
        api_path="/0/private/Balance",
        nonce="1616492376594",
        payload="nonce=1616492376594",
        api_secret_b64="c2VjcmV0",
    )
    assert sig1 == sig2
    assert len(sig1) > 10


def test_verify_live_permissions_denied_on_private_scope():
    class _Denied(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=True))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            raise RuntimeError("EGeneral:Permission denied")

        def open_orders(self):
            return {}

    ok, reason = _Denied().verify_live_permissions()
    assert ok is False
    assert "kraken_permission_denied:balance" in reason


def test_verify_live_permissions_ok():
    class _Ok(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=False))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            return {"ZUSD": "10"}

        def open_orders(self):
            return {}

    ok, reason = _Ok().verify_live_permissions()
    assert ok is True
    assert reason == "ok"


def test_verify_live_permissions_allow_unknown_on_transient_error():
    class _Transient(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=True))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            raise RuntimeError("temporary network timeout")

        def open_orders(self):
            return {}

    ok, reason = _Transient().verify_live_permissions()
    assert ok is True
    assert "permissions_unverified_operator_override" in reason


def test_verify_live_permissions_classifies_temporary_lockout() -> None:
    class _Lockout(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=False))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            raise RuntimeError("EGeneral:Temporary lockout")

        def open_orders(self):
            return {}

    ok, reason = _Lockout().verify_live_permissions()
    assert ok is False
    assert reason.startswith("kraken_temporary_lockout:balance")


def test_verify_live_permissions_temporary_lockout_override() -> None:
    class _LockoutOverride(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=True))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            raise RuntimeError("EGeneral:Temporary lockout")

        def open_orders(self):
            return {}

    ok, reason = _LockoutOverride().verify_live_permissions()
    assert ok is True
    assert "temporary_lockout_override" in reason


def test_verify_live_permissions_classifies_invalid_nonce() -> None:
    class _Nonce(KrakenSpotConnector):
        def __init__(self):
            super().__init__(KrakenSpotExecutionSettings(allow_unknown_permissions=False))
            self._api_key = "k"
            self._api_secret = "s"

        def balance(self):
            raise RuntimeError("EAPI:Invalid nonce")

        def open_orders(self):
            return {}

    ok, reason = _Nonce().verify_live_permissions()
    assert ok is False
    assert reason.startswith("kraken_invalid_nonce:balance")
