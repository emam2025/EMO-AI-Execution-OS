/**
 * OS Keyring Adapter — macOS Keychain / Windows Credential Manager / Linux Secret Service
 *
 * Uses @tauri-apps/plugin-keyring for cross-platform secure credential storage.
 * This is the ONLY allowed credential storage mechanism. File-based, env-based,
 * and localStorage-based storage are PROHIBITED.
 *
 * Fallback Policy: BLOCK — if the OS keyring is unavailable, the application
 * MUST NOT start. No fallback to plaintext or file storage.
 */
import type { ICredentialProvider, ProviderId, ProviderStatus, ProviderConfig } from "./types";
import { ALL_PROVIDERS, PROVIDER_META } from "./types";

const SERVICE_NAME = "emo-desktop";
const KEY_PREFIX = "provider_";

/**
 * Platform-native keyring adapter.
 *
 * In production this wraps @tauri-apps/plugin-keyring:
 *   - macOS: Security.framework (Keychain Services)
 *   - Windows: CredWriteW / CredReadW (Credential Manager)
 *   - Linux: libsecret (Secret Service / D-Bus)
 *
 * Skeleton implementation for Phase P2 — type-safe interface contract.
 */
class OsKeyringProvider implements ICredentialProvider {
  private _initialized = false;

  private async _ensureInitialized(): Promise<void> {
    if (this._initialized) return;
    // In production, this would invoke Tauri plugin initialization.
    // If the OS keychain is unavailable, throw to trigger BLOCK policy.
    this._initialized = true;
  }

  async saveKey(providerId: ProviderId, apiKey: string): Promise<void> {
    await this._ensureInitialized();
    return invoke_keyring_save(`${KEY_PREFIX}${providerId}`, apiKey);
  }

  async getKey(providerId: ProviderId): Promise<string | null> {
    await this._ensureInitialized();
    return invoke_keyring_get(`${KEY_PREFIX}${providerId}`);
  }

  async deleteKey(providerId: ProviderId): Promise<void> {
    await this._ensureInitialized();
    return invoke_keyring_delete(`${KEY_PREFIX}${providerId}`);
  }

  async hasKey(providerId: ProviderId): Promise<boolean> {
    const key = await this.getKey(providerId);
    return key !== null && key.length > 0;
  }

  async listConfiguredProviders(): Promise<ProviderId[]> {
    await this._ensureInitialized();
    const configured: ProviderId[] = [];
    for (const pid of ALL_PROVIDERS) {
      if (await this.hasKey(pid)) {
        configured.push(pid);
      }
    }
    return configured;
  }

  async getStatus(_providerId: ProviderId): Promise<ProviderStatus> {
    // Status requires gateway health check from the runtime.
    // This is a stub — real implementation calls testProviderConnection IPC command.
    return "active";
  }

  async rotateKey(providerId: ProviderId, newKey: string): Promise<void> {
    await this.saveKey(providerId, newKey);
  }
}

// ── Tauri plugin invocation stubs ─────────────────────
// In production, these call @tauri-apps/plugin-keyring.

async function invoke_keyring_save(key: string, value: string): Promise<void> {
  // Production: await invoke("plugin:keyring|set_password", { service: SERVICE_NAME, key, value });
  void key;
  void value;
}

async function invoke_keyring_get(key: string): Promise<string | null> {
  // Production: return await invoke("plugin:keyring|get_password", { service: SERVICE_NAME, key });
  void key;
  return null;
}

async function invoke_keyring_delete(key: string): Promise<void> {
  // Production: await invoke("plugin:keyring|delete_password", { service: SERVICE_NAME, key });
  void key;
}

// ── Singleton ────────────────────────────────────────
export const credentialProvider: ICredentialProvider = new OsKeyringProvider();
export default credentialProvider;
