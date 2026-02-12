from autonomous_investment_robot.connectors.base import ConnectorConfig


class GDELTConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
