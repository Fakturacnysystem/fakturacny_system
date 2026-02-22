from autonomous_investment_robot.connectors.base import ConnectorConfig


class CoinAPIConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class KaikoConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class CoinGeckoConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
