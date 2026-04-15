"use client";

import { startTransition, useEffect, useRef, useState } from "react";
import { getRuntimeAuthSnapshot } from "@/lib/auth/runtime-auth";
import { getRuntimeRepository } from "@/lib/runtime/repository";
import type {
  AlertRecord,
  BrainState,
  DecisionRecord,
  ExecutionState,
  HealthState,
  IncidentNoteInput,
  IncidentNoteResponse,
  IntegrityState,
  ReplayForensicsState,
  RuntimeControlAction,
  RuntimeControlRequest,
  RuntimeControlResponse,
  RuntimeDataSource,
  RuntimeEnvelope,
  RuntimeListResponse,
  RuntimeRunCatalog,
  RuntimeRunSelectionRequest,
  RuntimeRunSelectionResponse,
  RuntimeSummary,
  ShieldState,
  SymbolSnapshot,
} from "@/types/runtime";

export interface RuntimeQueryState<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  isRefreshing: boolean;
  source: RuntimeDataSource;
  configured: boolean;
  lastLoadedAt: string | null;
  refresh: () => void;
}

const repository = getRuntimeRepository();

function normalizeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "unknown_runtime_error";
}

function useRuntimeResource<T>(
  loadResource: () => Promise<RuntimeEnvelope<T>>,
  refreshMs = 12000,
  resourceKey = "default",
): RuntimeQueryState<T> {
  const loaderRef = useRef(loadResource);
  const loadVersionRef = useRef(0);
  const [state, setState] = useState<Omit<RuntimeQueryState<T>, "refresh">>({
    data: null,
    error: null,
    isLoading: true,
    isRefreshing: false,
    source: repository.source,
    configured: repository.configured,
    lastLoadedAt: null,
  });

  loaderRef.current = loadResource;

  const runLoad = async (
    kind: "initial" | "refresh",
    expectedVersion = loadVersionRef.current,
  ) => {
    setState((current) => ({
      ...current,
      isLoading: kind === "initial" && current.data === null,
      isRefreshing: kind === "refresh",
      error: null,
    }));
    try {
      const envelope = await loaderRef.current();
      if (expectedVersion !== loadVersionRef.current) {
        return;
      }
      setState({
        data: envelope.data,
        error: null,
        isLoading: false,
        isRefreshing: false,
        source: envelope.source,
        configured: envelope.configured,
        lastLoadedAt: new Date().toISOString(),
      });
    } catch (error) {
      if (expectedVersion !== loadVersionRef.current) {
        return;
      }
      setState((current) => ({
        ...current,
        isLoading: false,
        isRefreshing: false,
        error: normalizeError(error),
      }));
    }
  };

  useEffect(() => {
    loadVersionRef.current += 1;
    const activeVersion = loadVersionRef.current;
    void runLoad("initial", activeVersion);
    const intervalId = window.setInterval(() => {
      void runLoad("refresh", activeVersion);
    }, refreshMs);
    return () => {
      loadVersionRef.current += 1;
      window.clearInterval(intervalId);
    };
  }, [refreshMs, resourceKey]);

  return {
    ...state,
    refresh: () => {
      startTransition(() => {
        void runLoad("refresh");
      });
    },
  };
}

export function useRuntimeSummary() {
  return useRuntimeResource<RuntimeSummary>(() => repository.getSummary(), 12000);
}

export function useRuntimeRuns() {
  return useRuntimeResource<RuntimeRunCatalog>(() => repository.getRuns(), 12000);
}

export function useRuntimeSymbols() {
  return useRuntimeResource<RuntimeListResponse<SymbolSnapshot>>(
    () => repository.getSymbols(),
    12000,
  );
}

export function useRuntimeDecisions() {
  return useRuntimeResource<RuntimeListResponse<DecisionRecord>>(
    () => repository.getDecisions(),
    12000,
  );
}

export function useRuntimeAlerts() {
  return useRuntimeResource<RuntimeListResponse<AlertRecord>>(
    () => repository.getAlerts(),
    12000,
  );
}

export function useRuntimeHealth() {
  return useRuntimeResource<HealthState>(() => repository.getHealth(), 12000);
}

export function useRuntimeIntegrity() {
  return useRuntimeResource<IntegrityState>(() => repository.getIntegrity(), 12000);
}

export function useRuntimeBrain() {
  return useRuntimeResource<BrainState>(() => repository.getBrain(), 12000);
}

export function useRuntimeShield() {
  return useRuntimeResource<ShieldState>(() => repository.getShield(), 12000);
}

export function useRuntimeExecution() {
  return useRuntimeResource<ExecutionState>(() => repository.getExecution(), 12000);
}

export function useRuntimeReplay(runId: string) {
  return useRuntimeResource<ReplayForensicsState>(
    () => repository.getReplay(runId),
    18000,
    `replay:${runId}`,
  );
}

export function useRuntimeControls() {
  const [lastResponse, setLastResponse] = useState<RuntimeControlResponse | null>(null);
  const [pendingAction, setPendingAction] = useState<RuntimeControlAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  return {
    lastResponse,
    pendingAction,
    error,
    invoke: async (action: RuntimeControlAction, payload: RuntimeControlRequest) => {
      const auth = getRuntimeAuthSnapshot();
      setPendingAction(action);
      setError(null);
      try {
        const response = await repository.control(action, payload, auth);
        setLastResponse(response);
        return response;
      } catch (cause) {
        const message = normalizeError(cause);
        setError(message);
        throw cause;
      } finally {
        setPendingAction(null);
      }
    },
  };
}

export function useRuntimeRunSelection() {
  const [lastResponse, setLastResponse] = useState<RuntimeRunSelectionResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return {
    lastResponse,
    pending,
    error,
    submit: async (payload: RuntimeRunSelectionRequest) => {
      setPending(true);
      setError(null);
      try {
        const response = await repository.selectRun(payload);
        setLastResponse(response);
        return response;
      } catch (cause) {
        const message = normalizeError(cause);
        setError(message);
        throw cause;
      } finally {
        setPending(false);
      }
    },
  };
}

export function useIncidentNoteWriter() {
  const [lastResponse, setLastResponse] = useState<IncidentNoteResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return {
    lastResponse,
    pending,
    error,
    submit: async (payload: IncidentNoteInput) => {
      const auth = getRuntimeAuthSnapshot();
      setPending(true);
      setError(null);
      try {
        const response = await repository.writeIncidentNote(payload, auth);
        setLastResponse(response);
        return response;
      } catch (cause) {
        const message = normalizeError(cause);
        setError(message);
        throw cause;
      } finally {
        setPending(false);
      }
    },
  };
}
