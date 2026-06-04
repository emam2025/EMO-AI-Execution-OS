import React, { useState, useEffect, useCallback } from "react";
import { ProviderCard } from "./components/ProviderCard";
import { credentialProvider } from "../../../lib/credentials/os-keyring";
import { injectProviderKey } from "../../../lib/credentials/ephemeral_injection";
import type { ProviderId, ProviderStatus } from "../../../lib/credentials/types";
import { ALL_PROVIDERS, PROVIDER_META } from "../../../lib/credentials/types";

export const ProvidersSettings: React.FC = () => {
  const [statuses, setStatuses] = useState<Record<ProviderId, ProviderStatus>>({});
  const [keysExist, setKeysExist] = useState<Record<ProviderId, boolean>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const configured = await credentialProvider.listConfiguredProviders();
      const ks: Record<ProviderId, boolean> = {} as any;
      for (const pid of ALL_PROVIDERS) {
        ks[pid] = configured.includes(pid);
      }
      setKeysExist(ks);
      setLoading(false);
    })();
  }, []);

  const handleSave = useCallback(
    (pid: ProviderId) => async (key: string) => {
      await credentialProvider.saveKey(pid, key);
      await injectProviderKey(pid);
      setKeysExist((prev) => ({ ...prev, [pid]: true }));
    },
    []
  );

  const handleTest = useCallback(
    (pid: ProviderId) => async (): Promise<boolean> => {
      // Stub: in production, calls testProviderConnection IPC command.
      await new Promise((r) => setTimeout(r, 800));
      return true;
    },
    []
  );

  const handleRotate = useCallback(
    (pid: ProviderId) => async (newKey: string) => {
      await credentialProvider.rotateKey(pid, newKey);
      await injectProviderKey(pid);
    },
    []
  );

  const handleDelete = useCallback(
    (pid: ProviderId) => async () => {
      await credentialProvider.deleteKey(pid);
      setKeysExist((prev) => ({ ...prev, [pid]: false }));
      setStatuses((prev) => ({ ...prev, [pid]: "not_configured" }));
    },
    []
  );

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">AI Providers</h1>
        <p className="text-gray-400">Loading credential status...</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">AI Providers</h1>
          <p className="text-sm text-gray-500">
            Keys are stored in your OS keychain. Never saved to files or browser storage.
          </p>
        </div>
      </div>

      <div className="space-y-4 max-w-2xl">
        {ALL_PROVIDERS.map((pid) => (
          <ProviderCard
            key={pid}
            config={PROVIDER_META[pid]}
            status={statuses[pid] ?? "not_configured"}
            hasKey={!!keysExist[pid]}
            onSave={handleSave(pid)}
            onTest={handleTest(pid)}
            onRotate={handleRotate(pid)}
            onDelete={handleDelete(pid)}
          />
        ))}
      </div>

      <div className="mt-8 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
        <p className="font-semibold mb-1">🔒 Security Notice</p>
        <ul className="list-disc list-inside space-y-1 text-amber-600">
          <li>Keys are stored in OS keychain only — never in config files</li>
          <li>Keys are injected ephemerally into the runtime — cleared after 5 seconds</li>
          <li>No key data is logged, telemetried, or exposed in network headers</li>
          <li>Default/test keys are blocked in production mode</li>
        </ul>
      </div>
    </div>
  );
};
