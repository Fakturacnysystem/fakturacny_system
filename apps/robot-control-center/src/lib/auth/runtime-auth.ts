"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type RuntimeAuthStatus =
  | "anonymous"
  | "active"
  | "expired"
  | "invalid"
  | "provider-unavailable";

export interface RuntimeAuthSnapshot {
  operatorId: string;
  displayName: string;
  role: string;
  authSource: string;
  sessionId: string;
  expiresAt: string | null;
  status: RuntimeAuthStatus;
  providerStatus: "ready" | "unavailable";
  lastError: string | null;
}

interface RuntimeAuthState extends RuntimeAuthSnapshot {
  setIdentity: (payload: Partial<RuntimeAuthSnapshot>) => void;
  clearIdentity: () => void;
  markExpired: (reason?: string) => void;
  markInvalid: (reason?: string) => void;
  markProviderUnavailable: (reason?: string) => void;
  ensureSessionFresh: () => RuntimeAuthStatus;
}

function generateSessionId(): string {
  return crypto.randomUUID();
}

function buildDefaultAuthSnapshot(): RuntimeAuthSnapshot {
  return {
    operatorId: "",
    displayName: "",
    role: "observer",
    authSource: "local",
    sessionId: "",
    expiresAt: null,
    status: "anonymous",
    providerStatus: "ready",
    lastError: null,
  };
}

const noopStorage = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

export function deriveRuntimeAuthStatus(snapshot: RuntimeAuthSnapshot): RuntimeAuthStatus {
  if (snapshot.providerStatus === "unavailable") {
    return "provider-unavailable";
  }
  if (!snapshot.operatorId) {
    return "anonymous";
  }
  if (snapshot.status === "invalid") {
    return "invalid";
  }
  if (snapshot.expiresAt && new Date(snapshot.expiresAt).getTime() <= Date.now()) {
    return "expired";
  }
  return "active";
}

export function buildAuthorizationHeader(snapshot: RuntimeAuthSnapshot): string | null {
  if (deriveRuntimeAuthStatus(snapshot) !== "active" || !snapshot.sessionId) {
    return null;
  }
  return `Operator ${snapshot.operatorId}:${snapshot.sessionId}`;
}

export const useRuntimeAuthStore = create<RuntimeAuthState>()(
  persist(
    (set, get) => ({
      ...buildDefaultAuthSnapshot(),
      setIdentity: (payload) =>
        set((state) => {
          const sessionId = (payload.sessionId ?? state.sessionId) || generateSessionId();
          const next: RuntimeAuthSnapshot = {
            ...state,
            ...payload,
            operatorId: payload.operatorId ?? state.operatorId,
            displayName: payload.displayName ?? state.displayName,
            role: payload.role ?? state.role,
            authSource: payload.authSource ?? state.authSource,
            sessionId,
            expiresAt:
              payload.expiresAt ??
              state.expiresAt ??
              new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString(),
            status: payload.operatorId || state.operatorId ? "active" : state.status,
            providerStatus: "ready",
            lastError: null,
          };
          return {
            ...next,
            status: deriveRuntimeAuthStatus(next),
          };
        }),
      clearIdentity: () => set(buildDefaultAuthSnapshot()),
      markExpired: (reason = "session_expired") =>
        set((state) => ({
          ...state,
          status: "expired",
          lastError: reason,
        })),
      markInvalid: (reason = "invalid_session") =>
        set((state) => ({
          ...state,
          status: "invalid",
          lastError: reason,
        })),
      markProviderUnavailable: (reason = "auth_provider_unavailable") =>
        set((state) => ({
          ...state,
          providerStatus: "unavailable",
          status: "provider-unavailable",
          lastError: reason,
        })),
      ensureSessionFresh: () => {
        const snapshot = getRuntimeAuthSnapshot();
        if (snapshot.status === "expired" && get().status !== "expired") {
          set((state) => ({
            ...state,
            status: "expired",
            lastError: state.lastError ?? "session_expired",
          }));
        }
        return get().status;
      },
    }),
    {
      name: "rtc-auth",
      storage: createJSONStorage(() =>
        typeof window === "undefined" ? noopStorage : localStorage,
      ),
      partialize: (state) => ({
        operatorId: state.operatorId,
        displayName: state.displayName,
        role: state.role,
        authSource: state.authSource,
        sessionId: state.sessionId,
        expiresAt: state.expiresAt,
        status: state.status,
        providerStatus: state.providerStatus,
        lastError: state.lastError,
      }),
    },
  ),
);

export function getRuntimeAuthSnapshot(): RuntimeAuthSnapshot {
  const state = useRuntimeAuthStore.getState();
  const snapshot: RuntimeAuthSnapshot = {
    operatorId: state.operatorId,
    displayName: state.displayName,
    role: state.role,
    authSource: state.authSource,
    sessionId: state.sessionId,
    expiresAt: state.expiresAt,
    status: state.status,
    providerStatus: state.providerStatus,
    lastError: state.lastError,
  };
  return {
    ...snapshot,
    status: deriveRuntimeAuthStatus(snapshot),
  };
}

export const runtimeApiAuth = {
  getAuthorizationHeader(): string | null {
    return buildAuthorizationHeader(getRuntimeAuthSnapshot());
  },
};
