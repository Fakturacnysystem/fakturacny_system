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
