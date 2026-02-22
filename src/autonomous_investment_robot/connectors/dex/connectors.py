from autonomous_investment_robot.connectors.base import ConnectorConfig


class ZeroXConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class OneInchConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class UniswapSubgraphConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
