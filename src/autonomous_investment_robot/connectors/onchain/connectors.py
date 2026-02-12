from autonomous_investment_robot.connectors.base import ConnectorConfig


class TheGraphConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class DuneConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class GlassnodeConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class NansenConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class AlchemyConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class InfuraConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class ChainlinkConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
