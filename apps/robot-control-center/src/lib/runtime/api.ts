import { runtimeApiAuth } from "@/lib/auth/runtime-auth";
import type {
  AlertRecord,
  BrainState,
  DecisionRecord,
  ExecutionState,
  HealthState,
  IntegrityState,
  ReplayForensicsState,
  RuntimeIdentity,
  RuntimeRunCatalog,
  RuntimeRunSelectionRequest,
  RuntimeRunSelectionResponse,
  RuntimeSummary,
  ShieldState,
  SymbolSnapshot,
  IncidentNoteInput,
  IncidentNoteResponse,
  RuntimeControlAction,
  RuntimeControlRequest,
  RuntimeControlResponse,
} from "@/types/runtime";

const runtimeBaseUrl = process.env.NEXT_PUBLIC_RUNTIME_API_URL?.replace(/\/$/, "");

if (!runtimeBaseUrl) {
  console.info("Runtime API base URL missing — bridge fallback remains authoritative.");
}

export class RuntimeApiRequestError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown, detail: string) {
    super(detail);
    this.name = "RuntimeApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!runtimeBaseUrl) {
    throw new Error("runtime_api_unconfigured");
  }
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (init?.body) {
    headers["Content-Type"] = "application/json";
  }
  const authHeader = runtimeApiAuth.getAuthorizationHeader();
  if (authHeader) {
    headers.Authorization = authHeader;
  }
  const response = await fetch(`${runtimeBaseUrl}${path}`, {
    method: init?.method ?? "GET",
    headers,
    credentials: "include",
    body: init?.body,
  });
  if (!response.ok) {
    const text = await response.text();
    let payload: unknown = text;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = text;
    }
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `runtime_api_error:${response.status}:${text}`;
    throw new RuntimeApiRequestError(response.status, payload, detail);
  }
  return response.json();
}

export interface RuntimeApiSummary {
  providerId: string;
  mode: string;
  runId: string;
  runSelection: RuntimeSummary["runSelection"];
  runtimeIdentity: RuntimeIdentity;
  startedAt: string;
  uptimeSec: number;
  equityEur: number;
  freeCashEur: number;
  openPositions: number;
  openOrders: number;
  avgLatencyMs: number;
  wsConnected: boolean;
  restHealthy: boolean;
  stateKind: RuntimeSummary["bridge"]["health_status"];
  reasonCode?: string;
  reasonText?: string;
  lastUpdatedAt: string;
  performance?: RuntimeSummary["performance"];
}

export interface RuntimeApiListResponse<T> {
  items: T[];
  stateKind: string;
  lastUpdatedAt: string;
  reasonCode?: string;
  reasonText?: string;
  runtimeIdentity?: RuntimeIdentity;
}

export const runtimeApi = {
  summary: (): Promise<RuntimeApiSummary> => request("/runtime/summary"),
  runs: (): Promise<RuntimeRunCatalog> => request("/runtime/runs"),
  symbols: (): Promise<RuntimeApiListResponse<SymbolSnapshot>> => request("/runtime/symbols"),
  decisions: (): Promise<RuntimeApiListResponse<DecisionRecord>> => request("/runtime/decisions"),
  alerts: (): Promise<RuntimeApiListResponse<AlertRecord>> => request("/runtime/alerts"),
  health: (): Promise<HealthState> => request("/runtime/health"),
  integrity: (): Promise<IntegrityState> => request("/runtime/integrity"),
  brain: (): Promise<BrainState> => request("/runtime/brain"),
  shield: (): Promise<ShieldState> => request("/runtime/shield"),
  execution: (): Promise<ExecutionState> => request("/runtime/execution"),
  replay: (runId: string): Promise<ReplayForensicsState> => request(`/runtime/replay/${encodeURIComponent(runId)}`),
  selectRun: (payload: RuntimeRunSelectionRequest): Promise<RuntimeRunSelectionResponse> =>
    request("/runtime/select-run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  control: (action: RuntimeControlAction, payload: RuntimeControlRequest): Promise<RuntimeControlResponse> =>
    request(`/runtime/control/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  writeIncidentNote: (payload: IncidentNoteInput): Promise<IncidentNoteResponse> =>
    request("/runtime/incident-note", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export function runtimeApiAvailable(): boolean {
  return Boolean(runtimeBaseUrl);
}
