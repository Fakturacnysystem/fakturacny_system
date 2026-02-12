from autonomous_investment_robot.services.policy.allocator import BanditAllocator


def test_allocator_updates_and_cooldown():
    a = BanditAllocator(decay=0.9, max_weight=0.7, min_samples=1, fatal_sigma_loss=2.0, cooldown_steps=2)
    a.update_performance("trend", -3.0)
    w = a.allocate(["trend", "mean_reversion"])
    assert w["trend"] == 0.0
    a.step_cooldowns()
    a.step_cooldowns()
    w2 = a.allocate(["trend", "mean_reversion"])
    assert w2["trend"] >= 0.0
