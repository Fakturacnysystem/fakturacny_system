from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator


def run() -> None:
    settings = RobotSettings.from_env()
    orchestrator = RobotOrchestrator(settings)
    orchestrator.boot()


if __name__ == "__main__":
    run()
