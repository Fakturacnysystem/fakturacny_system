from autonomous_investment_robot.services.event_store.service import EventStore


def test_event_store_seeds_sequences_from_existing_streams(tmp_path):
    store = EventStore(str(tmp_path))
    store.append("orders", {"seq": store.next_seq("orders"), "type": "ORDER_INTENT"})
    store.append("orders", {"seq": store.next_seq("orders"), "type": "ORDER_UPDATE"})
    store.append("fills", {"seq": store.next_seq("fills"), "type": "FILL_ACCEPTED"})

    rehydrated = EventStore(str(tmp_path))

    assert rehydrated.last_seq("orders") == 2
    assert rehydrated.last_seq("fills") == 1
    assert rehydrated.latest("orders") == {"seq": 2, "type": "ORDER_UPDATE"}
    assert rehydrated.next_seq("orders") == 3


def test_event_store_returns_empty_state_for_missing_stream(tmp_path):
    store = EventStore(str(tmp_path))

    assert store.load("risk") == []
    assert store.last_seq("risk") == 0
    assert store.latest("risk") is None
