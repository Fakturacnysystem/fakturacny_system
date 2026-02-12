class RawStoreService:
    """Immutable object writes + append-only event log interface."""

    def write_object(self, bucket: str, key: str, body: bytes) -> str:
        return f"s3://{bucket}/{key}"

    def append_log(self, stream: str, record: dict) -> None:
        return None
