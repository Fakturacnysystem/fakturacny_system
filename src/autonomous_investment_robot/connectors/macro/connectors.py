from autonomous_investment_robot.connectors.base import ConnectorConfig


class ECBDataPortalConnector:
    """Targets ECB Data Portal API (post-SDW migration stable path)."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config


class FREDConnector:
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
