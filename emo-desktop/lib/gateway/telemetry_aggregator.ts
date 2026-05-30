/**
 * TelemetryAggregator — Aggregates cost, latency, and failover metrics
 * from runtime events and pushes to Zustand store every 500ms.
 *
 * Zero core dependencies — pure TypeScript aggregation + store binding.
 */

import type { GatewayMetrics } from "../../ui/types/telemetry";

export interface RawTelemetryEvent {
  type: string;
  timestamp: string;
  payload: {
    provider_id?: string;
    cost_per_token?: number;
    tokens_used?: number;
    latency_ms?: number;
    status_code?: number;
    failover?: boolean;
  };
}

export interface TelemetrySnapshot {
  cost_per_token: number;
  total_session_cost: number;
  avg_latency_ms: number;
  failover_count: number;
  provider_success_rate: number;
  total_requests: number;
  failed_requests: number;
}

export class TelemetryAggregator {
  private costs: number[];
  private latencies: number[];
  private failoverCount: number;
  private totalRequests: number;
  private failedRequests: number;
  private intervalId: ReturnType<typeof setInterval> | null;
  private onSnapshot: ((snapshot: TelemetrySnapshot) => void) | null;

  constructor() {
    this.costs = [];
    this.latencies = [];
    this.failoverCount = 0;
    this.totalRequests = 0;
    this.failedRequests = 0;
    this.intervalId = null;
    this.onSnapshot = null;
  }

  setOnSnapshot(cb: (snapshot: TelemetrySnapshot) => void): void {
    this.onSnapshot = cb;
  }

  /**
   * Ingest a raw runtime event and extract telemetry signals.
   */
  ingest(event: RawTelemetryEvent): void {
    const p = event.payload;
    if (!p) return;

    if (p.cost_per_token !== undefined && p.tokens_used !== undefined) {
      this.costs.push(p.cost_per_token * p.tokens_used);
    }

    if (p.latency_ms !== undefined) {
      this.latencies.push(p.latency_ms);
    }

    if (p.failover === true) {
      this.failoverCount++;
    }

    this.totalRequests++;

    if (p.status_code !== undefined && p.status_code >= 400) {
      this.failedRequests++;
    }
  }

  /**
   * Start periodic aggregation — emits snapshot every `intervalMs`.
   */
  start(intervalMs: number = 500): void {
    if (this.intervalId) return;
    this.intervalId = setInterval(() => {
      this.emitSnapshot();
    }, intervalMs);
  }

  /**
   * Stop periodic aggregation.
   */
  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  /**
   * Compute a snapshot of current telemetry.
   */
  getSnapshot(): TelemetrySnapshot {
    const avgLatency =
      this.latencies.length > 0
        ? this.latencies.reduce((a, b) => a + b, 0) / this.latencies.length
        : 0;

    const totalCost = this.costs.reduce((a, b) => a + b, 0);

    const avgCost =
      this.costs.length > 0 ? totalCost / this.costs.length : 0;

    const successRate =
      this.totalRequests > 0
        ? (this.totalRequests - this.failedRequests) / this.totalRequests
        : 1;

    return {
      cost_per_token: Math.round(avgCost * 1e6) / 1e6,
      total_session_cost: Math.round(totalCost * 1e6) / 1e6,
      avg_latency_ms: Math.round(avgLatency * 100) / 100,
      failover_count: this.failoverCount,
      provider_success_rate: Math.round(successRate * 10000) / 100,
      total_requests: this.totalRequests,
      failed_requests: this.failedRequests,
    };
  }

  private emitSnapshot(): void {
    if (this.onSnapshot) {
      this.onSnapshot(this.getSnapshot());
    }
  }

  reset(): void {
    this.costs = [];
    this.latencies = [];
    this.failoverCount = 0;
    this.totalRequests = 0;
    this.failedRequests = 0;
  }

  destroy(): void {
    this.stop();
    this.onSnapshot = null;
    this.reset();
  }
}
