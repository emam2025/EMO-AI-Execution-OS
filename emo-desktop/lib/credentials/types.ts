/**
 * Credential Vault Types — ICredentialProvider & ProviderStatus
 */
export type ProviderId =
  | "openai"
  | "anthropic"
  | "gemini"
  | "openrouter"
  | "groq"
  | "together"
  | "deepseek"
  | "ollama"
  | "vllm"
  | "openai_compatible";

export const ALL_PROVIDERS: ProviderId[] = [
  "openai",
  "anthropic",
  "gemini",
  "openrouter",
  "groq",
  "together",
  "deepseek",
  "ollama",
  "vllm",
  "openai_compatible",
];

export type ProviderStatus = "active" | "rate_limited" | "invalid_key" | "not_configured";

export type ProviderConfig = {
  id: ProviderId;
  label: string;
  baseUrl?: string;
  requiresBaseUrl: boolean;
  supportsCustomModels: boolean;
  defaultModel?: string;
};

export const PROVIDER_META: Record<ProviderId, ProviderConfig> = {
  openai: {
    id: "openai",
    label: "OpenAI",
    requiresBaseUrl: false,
    supportsCustomModels: false,
    defaultModel: "gpt-4o",
  },
  anthropic: {
    id: "anthropic",
    label: "Anthropic",
    requiresBaseUrl: false,
    supportsCustomModels: false,
    defaultModel: "claude-3-5-sonnet",
  },
  gemini: {
    id: "gemini",
    label: "Gemini",
    requiresBaseUrl: false,
    supportsCustomModels: false,
    defaultModel: "gemini-2.0-flash",
  },
  openrouter: {
    id: "openrouter",
    label: "OpenRouter",
    requiresBaseUrl: false,
    supportsCustomModels: true,
    defaultModel: "openrouter/auto",
  },
  groq: {
    id: "groq",
    label: "Groq",
    requiresBaseUrl: false,
    supportsCustomModels: false,
    defaultModel: "llama-3.3-70b",
  },
  together: {
    id: "together",
    label: "Together AI",
    requiresBaseUrl: false,
    supportsCustomModels: true,
    defaultModel: "mistralai/Mixtral-8x22B",
  },
  deepseek: {
    id: "deepseek",
    label: "DeepSeek",
    requiresBaseUrl: false,
    supportsCustomModels: false,
    defaultModel: "deepseek-chat",
  },
  ollama: {
    id: "ollama",
    label: "Ollama (Local)",
    requiresBaseUrl: true,
    supportsCustomModels: true,
    defaultModel: "llama3",
  },
  vllm: {
    id: "vllm",
    label: "vLLM (Local)",
    requiresBaseUrl: true,
    supportsCustomModels: true,
    defaultModel: "mistralai/Mistral-7B",
  },
  openai_compatible: {
    id: "openai_compatible",
    label: "OpenAI-Compatible",
    requiresBaseUrl: true,
    supportsCustomModels: true,
    defaultModel: "custom-model",
  },
};

export interface ICredentialProvider {
  /** Store a provider API key in the OS keychain. */
  saveKey(providerId: ProviderId, apiKey: string): Promise<void>;

  /** Retrieve a provider API key from the OS keychain. */
  getKey(providerId: ProviderId): Promise<string | null>;

  /** Delete a provider API key from the OS keychain. */
  deleteKey(providerId: ProviderId): Promise<void>;

  /** Check if a key exists in the OS keychain. */
  hasKey(providerId: ProviderId): Promise<boolean>;

  /** List all provider IDs that have keys stored. */
  listConfiguredProviders(): Promise<ProviderId[]>;

  /** Get the status of a provider (requires gateway health check). */
  getStatus(providerId: ProviderId): Promise<ProviderStatus>;

  /** Rotate a key — replace old key with new key. */
  rotateKey(providerId: ProviderId, newKey: string): Promise<void>;
}

export type EphemeralInjectionResult = {
  providerId: ProviderId;
  injected: boolean;
  method: "stdin" | "env_isolated";
  cleared_at: number | null;
};
