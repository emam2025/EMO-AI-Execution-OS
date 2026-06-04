import { createDecipheriv } from "crypto";

const ENCRYPTION_KEY = process.env.EMO_PILOT_ENCRYPTION_KEY || "emo-pilot-dev-key-32chars__";

export interface MetricReport {
  companyId: string;
  date: string;
  metrics: Record<string, number>;
  tags?: Record<string, string>;
}

export interface AggregatedMetric {
  name: string;
  avg: number;
  min: number;
  max: number;
  sum: number;
  count: number;
  stdDev: number;
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface Anomaly {
  metricName: string;
  date: string;
  value: number;
  mean: number;
  stdDev: number;
  zScore: number;
  severity: "low" | "medium" | "high";
}

const reportStore: MetricReport[] = [];

export function ingestReport(report: MetricReport): void {
  reportStore.push({ ...report, metrics: { ...report.metrics } });
}

export function aggregateDailyMetrics(companyId?: string, date?: string): AggregatedMetric[] {
  let filtered = reportStore;
  if (companyId) {
    filtered = filtered.filter((r) => r.companyId === companyId);
  }
  if (date) {
    filtered = filtered.filter((r) => r.date === date);
  }

  const grouped = new Map<string, number[]>();

  for (const report of filtered) {
    for (const [name, value] of Object.entries(report.metrics)) {
      if (!grouped.has(name)) {
        grouped.set(name, []);
      }
      grouped.get(name)!.push(value);
    }
  }

  const result: AggregatedMetric[] = [];
  for (const [name, values] of grouped) {
    const sum = values.reduce((a, b) => a + b, 0);
    const count = values.length;
    const avg = sum / count;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const variance = values.reduce((acc, v) => acc + (v - avg) ** 2, 0) / count;
    const stdDev = Math.sqrt(variance);

    result.push({ name, avg, min, max, sum, count, stdDev });
  }

  return result.sort((a, b) => b.count - a.count);
}

export function getTrendView(metricName: string, timeframe: number = 7): TrendPoint[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - timeframe);

  const filtered = reportStore.filter((r) => {
    return r.metrics[metricName] !== undefined;
  });

  const grouped = new Map<string, { sum: number; count: number }>();

  for (const report of filtered) {
    const value = report.metrics[metricName];
    if (value === undefined) continue;
    const existing = grouped.get(report.date);
    if (existing) {
      existing.sum += value;
      existing.count++;
    } else {
      grouped.set(report.date, { sum: value, count: 1 });
    }
  }

  return Array.from(grouped.entries())
    .map(([date, { sum, count }]) => ({ date, value: sum / count }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function detectAnomalies(threshold: number = 2): Anomaly[] {
  const anomalies: Anomaly[] = [];
  const aggregated = aggregateDailyMetrics();

  for (const metric of aggregated) {
    if (metric.count < 3) continue;

    const values = reportStore
      .filter((r) => r.metrics[metric.name] !== undefined)
      .map((r) => ({ date: r.date, value: r.metrics[metric.name] }));

    for (const point of values) {
      const zScore = metric.stdDev > 0 ? Math.abs((point.value - metric.avg) / metric.stdDev) : 0;
      if (zScore > threshold) {
        let severity: "low" | "medium" | "high";
        if (zScore > 3.5) severity = "high";
        else if (zScore > 2.5) severity = "medium";
        else severity = "low";

        anomalies.push({
          metricName: metric.name,
          date: point.date,
          value: point.value,
          mean: metric.avg,
          stdDev: metric.stdDev,
          zScore,
          severity,
        });
      }
    }
  }

  return anomalies.sort((a, b) => b.zScore - a.zScore);
}

export function decryptReport(encryptedData: string): string {
  const key = Buffer.from(ENCRYPTION_KEY.padEnd(32, "_").slice(0, 32));
  const parts = encryptedData.split(":");
  if (parts.length < 2) throw new Error("invalid encrypted format");
  const iv = Buffer.from(parts[0], "hex");
  const encrypted = Buffer.from(parts.slice(1).join(":"), "hex");
  const decipher = createDecipheriv("aes-256-cbc", key, iv);
  return decipher.update(encrypted) + decipher.final("utf8");
}

export function ingestEncryptedReport(encryptedData: string): boolean {
  try {
    const decrypted = decryptReport(encryptedData);
    const report: MetricReport = JSON.parse(decrypted);
    ingestReport(report);
    return true;
  } catch {
    return false;
  }
}

export function clearAllReports(): void {
  reportStore.length = 0;
}

export function getReportCount(): number {
  return reportStore.length;
}
