import type { RunbookContract } from "@/types/contracts";

export const runbookCatalog: RunbookContract = {
  severities: [
    {
      severity: "SEV-1",
      examples: [
        "Emergency flatten required.",
        "Unsafe execution state or corrupted control state.",
        "Critical backend/runtime mismatch.",
      ],
    },
    {
      severity: "SEV-2",
      examples: [
        "Stale market data with execution impact.",
        "Degraded integrity or repeated bridge/backend failures.",
        "Major replay or forensics inconsistency.",
      ],
    },
    {
      severity: "SEV-3",
      examples: [
        "Partial artifact availability.",
        "Non-critical diagnostics degradation.",
        "UI/bridge mismatch without execution risk.",
      ],
    },
  ],
  procedures: [
    {
      title: "Pause",
      whenToUse: ["Suspicious behavior", "Pre-maintenance", "Manual inspection"],
      steps: [
        "Confirm the pause command with named operator identity.",
        "Verify effective state and audit reference returned by the runtime.",
        "Add an incident note when the reason is operational.",
      ],
    },
    {
      title: "Resume",
      whenToUse: ["Health is acceptable", "Critical blockers are cleared"],
      steps: [
        "Verify health is not in danger state.",
        "Verify integrity blockers are understood or cleared.",
        "Record explicit resume reason before resuming opens.",
      ],
    },
    {
      title: "Freeze",
      whenToUse: ["Integrity state is unclear", "Human intervention required urgently"],
      steps: [
        "Freeze new openings immediately.",
        "Open diagnostics and capture evidence bundle.",
        "Escalate to replay review if ambiguity persists.",
      ],
    },
    {
      title: "Emergency Flatten",
      whenToUse: ["Immediate position exit is required", "Exposure is unacceptable"],
      steps: [
        "Confirm flatten response and audit reference.",
        "Open diagnostics and capture replay inputs.",
        "Write incident note with operator, timestamp, action and next review step.",
      ],
    },
  ],
  replayChecklist: [
    "Open Replay Lab.",
    "Inspect run timeline, incidents and analog matches.",
    "Review counterfactuals and PnL attribution.",
    "Document root-cause hypothesis.",
    "Classify severity and define corrective action.",
  ],
};
