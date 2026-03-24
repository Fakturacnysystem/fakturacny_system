from autonomous_investment_robot.services.distributed_runtime.service import DistributedRuntimeService


def test_distributed_runtime_defaults_to_disabled_proof_mode():
    svc = DistributedRuntimeService()

    selector = svc.selector()
    health = svc.health_report()

    assert selector.enabled is False
    assert selector.reason == "distributed_runtime_disabled_by_default"
    assert health.mode == "single_process"
    assert health.metadata["proof_only"] is True
