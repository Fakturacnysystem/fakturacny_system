class DataQAService:
    def validate(self, event: dict) -> tuple[bool, list[str]]:
        issues = []
        if "ts" not in event:
            issues.append("missing_ts")
        return (len(issues) == 0, issues)
