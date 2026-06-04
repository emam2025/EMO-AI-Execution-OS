import { encryptReport, getAggregatedMetrics, getPilotDuration, isPilotModeEnabled, getActiveCompanyId } from "./pilot-mode-manager";

interface DailyReport {
  date: string;
  companyId: string;
  uptimeMs: number;
  metrics: { name: string; avg: number; count: number }[];
  summary: {
    totalMetrics: number;
    uniqueMetrics: number;
    averageLatency: number;
    healthScore: number;
  };
}

export function generateDailyReport(): DailyReport | null {
  if (!isPilotModeEnabled() || !getActiveCompanyId()) return null;

  const aggregated = getAggregatedMetrics();
  const uptime = getPilotDuration();
  const totalMetrics = aggregated.reduce((s, m) => s + m.count, 0);

  const latencyMetrics = aggregated.filter((m) => m.name.includes("latency"));
  const avgLatency = latencyMetrics.length > 0
    ? latencyMetrics.reduce((s, m) => s + m.avg, 0) / latencyMetrics.length
    : 0;

  const successMetrics = aggregated.filter((m) => m.name.includes("success"));
  const healthScore = successMetrics.length > 0
    ? successMetrics.reduce((s, m) => s + m.avg, 0) / successMetrics.length
    : 1;

  const report: DailyReport = {
    date: new Date().toISOString().split("T")[0],
    companyId: getActiveCompanyId()!,
    uptimeMs: uptime,
    metrics: aggregated.map((m) => ({ name: m.name, avg: m.avg, count: m.count })),
    summary: {
      totalMetrics,
      uniqueMetrics: aggregated.length,
      averageLatency: Math.round(avgLatency * 100) / 100,
      healthScore: Math.round(healthScore * 100) / 100,
    },
  };

  return report;
}

export function submitDailyReport(): { submitted: boolean; encryptedSize: number; error?: string } {
  const report = generateDailyReport();
  if (!report) {
    return { submitted: false, encryptedSize: 0, error: "pilot mode not active" };
  }

  try {
    const serialized = JSON.stringify(report);
    const encrypted = encryptReport(serialized);
    return { submitted: true, encryptedSize: encrypted.length };
  } catch (err) {
    return { submitted: false, encryptedSize: 0, error: String(err) };
  }
}
