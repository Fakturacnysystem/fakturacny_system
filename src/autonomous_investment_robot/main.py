from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator


def run_with_config(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    orchestrator = RobotOrchestrator(settings)
    return orchestrator.boot()
