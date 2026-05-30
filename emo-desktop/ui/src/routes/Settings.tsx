import React from "react";

export const Settings: React.FC = () => {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <div className="space-y-4">
        <div className="p-4 border rounded-lg">
          <h2 className="font-semibold">Runtime Connection</h2>
          <p className="text-sm text-gray-500">
            Host: localhost : Port: 8080
          </p>
        </div>
        <div className="p-4 border rounded-lg">
          <h2 className="font-semibold">Authentication</h2>
          <p className="text-sm text-gray-500">
            Session token managed by RuntimeClient. Re-authenticate by
            restarting the runtime.
          </p>
        </div>
        <div className="p-4 border rounded-lg">
          <h2 className="font-semibold">About</h2>
          <p className="text-sm text-gray-500">
            EMO Desktop v0.1.0-product-alpha — Phase P1 IPC Skeleton
          </p>
          <p className="text-sm text-gray-500">
            Runtime: v4.15.0-delivery-ready (R1)
          </p>
        </div>
      </div>
    </div>
  );
};
