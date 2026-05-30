/**
 * Zustand store — Runtime state, events, telemetry, and trace cache.
 *
 * All state is managed through RuntimeClient (Fetch + WebSocket).
 * No direct runtime imports — fully decoupled from core/.
 */
import { create } from "zustand";
import type {
  RuntimeSession,
  RuntimeHealth,
  RuntimeTelemetry,
  RuntimeEvent,
  ExecutionTrace,
  GatewayMetrics,
  GatewayRoutingStatus,
} from "../../types/telemetry";

interface RuntimeState {
  // Session
  session: RuntimeSession | null;
  health: RuntimeHealth | null;
  telemetry: RuntimeTelemetry | null;

  // Event stream
  events: RuntimeEvent[];
  eventFilter: string | null;

  // Trace cache
  traceCache: Map<string, ExecutionTrace>;

  // Connection
  isConnected: boolean;
  error: string | null;

  // Gateway routing
  gatewayMetrics: GatewayMetrics | null;
  routingStatus: GatewayRoutingStatus | null;

  // Actions
  setSession: (session: RuntimeSession | null) => void;
  setHealth: (health: RuntimeHealth) => void;
  setTelemetry: (t: RuntimeTelemetry) => void;
  pushEvent: (event: RuntimeEvent) => void;
  setEventFilter: (traceId: string | null) => void;
  cacheTrace: (trace: ExecutionTrace) => void;
  setConnected: (v: boolean) => void;
  setError: (e: string | null) => void;
  setGatewayMetrics: (m: GatewayMetrics) => void;
  setRoutingStatus: (s: GatewayRoutingStatus) => void;
  reset: () => void;
}

const initialState = {
  session: null,
  health: null,
  telemetry: null,
  events: [],
  eventFilter: null,
  traceCache: new Map(),
  isConnected: false,
  error: null,
  gatewayMetrics: null,
  routingStatus: null,
};

export const useRuntimeStore = create<RuntimeState>((set, get) => ({
  ...initialState,

  setSession: (session) => set({ session }),

  setHealth: (health) => set({ health }),

  setTelemetry: (t) => set({ telemetry: t }),

  pushEvent: (event) => {
    const { eventFilter, events } = get();
    const filtered =
      eventFilter && eventFilter !== event.trace_id
        ? events
        : [...events.slice(-999), event];
    // Keep last 1000 events
    if (filtered.length > 1000) filtered.shift();
    set({ events: filtered });
  },

  setEventFilter: (traceId) => set({ eventFilter: traceId }),

  cacheTrace: (trace) => {
    const traceCache = new Map(get().traceCache);
    traceCache.set(trace.trace_id, trace);
    // Keep last 50 traces
    if (traceCache.size > 50) {
      const firstKey = traceCache.keys().next().value;
      if (firstKey) traceCache.delete(firstKey);
    }
    set({ traceCache });
  },

  setConnected: (v) => set({ isConnected: v }),

  setError: (e) => set({ error: e }),

  setGatewayMetrics: (m) => set({ gatewayMetrics: m }),

  setRoutingStatus: (s) => set({ routingStatus: s }),

  reset: () => set(initialState),
}));
