import React from "react";
import { useRuntimeStore } from "../stores/runtime";

export const RuntimeMonitor: React.FC = () => {
  const { telemetry, events, isConnected } = useRuntimeStore();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Runtime Monitor</h1>
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="p-3 bg-gray-100 rounded text-center">
          <p className="text-lg font-bold">{telemetry?.cpu_usage ?? "--"}%</p>
          <p className="text-sm text-gray-500">CPU</p>
        </div>
        <div className="p-3 bg-gray-100 rounded text-center">
          <p className="text-lg font-bold">{telemetry?.memory_usage ?? "--"} MB</p>
          <p className="text-sm text-gray-500">Memory</p>
        </div>
        <div className="p-3 bg-gray-100 rounded text-center">
          <p className="text-lg font-bold">{telemetry?.event_latency_ms ?? "--"} ms</p>
          <p className="text-sm text-gray-500">Event Latency</p>
        </div>
      </div>
      <div className="border rounded-lg p-4">
        <h2 className="font-semibold mb-2">
          Event Stream {isConnected ? "(live)" : "(disconnected)"}
        </h2>
        <div className="h-64 overflow-y-auto space-y-1 text-sm font-mono">
          {events.length === 0 && (
            <p className="text-gray-400">No events yet. Connect to runtime.</p>
          )}
          {events.map((e, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-gray-400 shrink-0">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className="text-blue-600 shrink-0">{e.type}</span>
              <span className="text-gray-500 truncate">
                {e.trace_id ?? ""}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
