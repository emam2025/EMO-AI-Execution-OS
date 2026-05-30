import React from "react";
import { useRuntimeStore } from "../stores/runtime";

export const Dashboard: React.FC = () => {
  const { health, telemetry, isConnected } = useRuntimeStore();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 border rounded-lg">
          <h2 className="font-semibold">Runtime Status</h2>
          <p>Status: {health?.status ?? "disconnected"}</p>
          <p>Uptime: {health?.uptime_seconds ?? 0}s</p>
          <p>WebSocket: {isConnected ? "connected" : "disconnected"}</p>
        </div>
        <div className="p-4 border rounded-lg">
          <h2 className="font-semibold">Telemetry</h2>
          <p>CPU: {telemetry?.cpu_usage ?? "--"}%</p>
          <p>Memory: {telemetry?.memory_usage ?? "--"} MB</p>
          <p>Active Agents: {telemetry?.active_agents ?? "--"}</p>
          <p>Queued Tasks: {telemetry?.queued_tasks ?? "--"}</p>
        </div>
      </div>
    </div>
  );
};
