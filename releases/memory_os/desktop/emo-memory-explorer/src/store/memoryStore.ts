import { create } from "zustand";

export interface MemoryStats {
  totalEntries: number;
  totalGraphNodes: number;
  totalEdges: number;
  projectsCount: number;
  agentsActive: number;
  lastOptimized: string;
}

export interface SpaceInfo {
  id: string;
  type: "project" | "agent";
  name: string;
  entryCount: number;
  lastActivity: string;
}

export interface AuditRecord {
  entryId: string;
  action: string;
  targetType: string;
  targetId: string;
  reason: string;
  timestamp: string;
  sha256Hash: string;
  chainVerified: boolean;
}

export interface RetentionConfig {
  maxEntries: number;
  ttlDays: number;
  archiveAfterDays: number;
  hardDeleteAfterDays: number;
  action: "archive" | "hard_delete" | "warn";
}

interface MemoryStore {
  stats: MemoryStats;
  spaces: SpaceInfo[];
  auditLog: AuditRecord[];
  retention: RetentionConfig;
  loading: Record<string, boolean>;
  setStats: (s: MemoryStats) => void;
  setSpaces: (spaces: SpaceInfo[]) => void;
  setAuditLog: (log: AuditRecord[]) => void;
  setRetention: (r: RetentionConfig) => void;
  setLoading: (key: string, val: boolean) => void;
}

export const useMemoryStore = create<MemoryStore>((set) => ({
  stats: {
    totalEntries: 0,
    totalGraphNodes: 0,
    totalEdges: 0,
    projectsCount: 0,
    agentsActive: 0,
    lastOptimized: "—",
  },
  spaces: [],
  auditLog: [],
  retention: {
    maxEntries: 100000,
    ttlDays: 365,
    archiveAfterDays: 180,
    hardDeleteAfterDays: 730,
    action: "archive",
  },
  loading: {},
  setStats: (stats) => set({ stats }),
  setSpaces: (spaces) => set({ spaces }),
  setAuditLog: (auditLog) => set({ auditLog }),
  setRetention: (retention) => set({ retention }),
  setLoading: (key, val) =>
    set((state) => ({ loading: { ...state.loading, [key]: val } })),
}));
