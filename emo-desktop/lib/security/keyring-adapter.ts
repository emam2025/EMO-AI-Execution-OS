/**
 * Keyring Adapter — OS Keychain Integration
 *
 * Cross-platform secure credential storage using tauri-plugin-keyring.
 * macOS: Keychain Services (Security.framework)
 * Windows: Credential Manager (CredWriteW/CredReadW)
 * Linux: libsecret (Secret Service / D-Bus)
 *
 * BLOCK policy: if OS keyring is unavailable, the application MUST NOT start.
 * No fallback to .env, config.json, localStorage, or any file-based storage.
 */
import type { ProviderId } from "../credentials/types";

const SERVICE_NAME = "emo-desktop";
const KEY_PREFIX = "provider_";

interface KeyringAdapter {
  storeKey(providerId: ProviderId, key: string): Promise<void>;
  getKey(providerId: ProviderId): Promise<string | null>;
  deleteKey(providerId: ProviderId): Promise<void>;
  hasKey(providerId: ProviderId): Promise<boolean>;
  clearAllKeys(): Promise<void>;
  listConfiguredProviders(): Promise<ProviderId[]>;
}

async function invokeKeyringSave(key: string, value: string): Promise<void> {
  try {
    // Production: await invoke("plugin:keyring|set_password", { service: SERVICE_NAME, key, value });
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("plugin:keyring|set_password", { service: SERVICE_NAME, key, value });
  } catch {
    throw new Error(`Keyring unavailable — BLOCK policy enforced`);
  }
}

async function invokeKeyringGet(key: string): Promise<string | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<string | null>("plugin:keyring|get_password", { service: SERVICE_NAME, key });
  } catch {
    return null;
  }
}

async function invokeKeyringDelete(key: string): Promise<void> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("plugin:keyring|delete_password", { service: SERVICE_NAME, key });
  } catch {
    // Silent fail — key may not exist
  }
}

const ALL_PROVIDERS: ProviderId[] = [
  "openai", "anthropic", "gemini", "openrouter", "groq",
  "together", "deepseek", "ollama", "vllm", "openai_compatible",
];

export const keyring: KeyringAdapter = {
  async storeKey(providerId, key): Promise<void> {
    if (!key || key.length < 8) {
      throw new Error("Invalid key — minimum 8 characters required");
    }
    await invokeKeyringSave(`${KEY_PREFIX}${providerId}`, key);
  },

  async getKey(providerId): Promise<string | null> {
    return invokeKeyringGet(`${KEY_PREFIX}${providerId}`);
  },

  async deleteKey(providerId): Promise<void> {
    await invokeKeyringDelete(`${KEY_PREFIX}${providerId}`);
  },

  async hasKey(providerId): Promise<boolean> {
    const key = await this.getKey(providerId);
    return key !== null && key.length > 0;
  },

  async clearAllKeys(): Promise<void> {
    for (const pid of ALL_PROVIDERS) {
      await this.deleteKey(pid);
    }
  },

  async listConfiguredProviders(): Promise<ProviderId[]> {
    const configured: ProviderId[] = [];
    for (const pid of ALL_PROVIDERS) {
      if (await this.hasKey(pid)) {
        configured.push(pid);
      }
    }
    return configured;
  },
};
