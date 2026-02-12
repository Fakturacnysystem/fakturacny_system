from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.core.orchestrator import RobotOrchestrator
from autonomous_investment_robot.services.replay.engine import ReplayEngine


def run_with_config(config_path: str) -> dict:
    settings = RobotSettings.from_file(config_path)
    orchestrator = RobotOrchestrator(settings)
    return orchestrator.boot()


def run_replay(config_path: str, source: str = "fixtures") -> dict:
    settings = RobotSettings.from_file(config_path)
    symbol = settings.universe[0]
    engine = ReplayEngine()
    events = engine.from_csv(settings.fixtures.ohlcv_csv, symbol=symbol, venue=source)
    return {"events": len(events), "source": source}
