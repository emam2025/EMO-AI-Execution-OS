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

export interface Project {
  id: string;
  name: string;
  created_at: string;
  agent_count: number;
  memory_space: string;
  status: "active" | "idle" | "archived";
}

export interface SkillEntry {
  id: string;
  name: string;
  tier: "extracted" | "validated" | "production" | "deprecated";
  accuracy: number;
  usage_count: number;
  source: string;
  created_at: string;
}

export interface KnowledgeNode {
  id: string;
  type: "memory" | "entity" | "concept";
  label: string;
  children: KnowledgeNode[];
}

interface RuntimeState {
  session: RuntimeSession | null;
  health: RuntimeHealth | null;
  telemetry: RuntimeTelemetry | null;
  events: RuntimeEvent[];
  eventFilter: string | null;
  traceCache: Map<string, ExecutionTrace>;
  isConnected: boolean;
  error: string | null;
  gatewayMetrics: GatewayMetrics | null;
  routingStatus: GatewayRoutingStatus | null;

  projects: Project[];
  skills: SkillEntry[];
  knowledgeTree: KnowledgeNode[];

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
  setProjects: (projects: Project[]) => void;
  setSkills: (skills: SkillEntry[]) => void;
  setKnowledgeTree: (tree: KnowledgeNode[]) => void;
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
  projects: [] as Project[],
  skills: [] as SkillEntry[],
  knowledgeTree: [] as KnowledgeNode[],
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
    if (filtered.length > 1000) filtered.shift();
    set({ events: filtered });
  },

  setEventFilter: (traceId) => set({ eventFilter: traceId }),

  cacheTrace: (trace) => {
    const traceCache = new Map(get().traceCache);
    traceCache.set(trace.trace_id, trace);
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
  setProjects: (projects) => set({ projects }),
  setSkills: (skills) => set({ skills }),
  setKnowledgeTree: (tree) => set({ knowledgeTree: tree }),
  reset: () => set(initialState),
}));
