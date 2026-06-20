/**
 * EMO AI Design System — Design Tokens
 *
 * Enterprise-grade design system with Dark/Light mode support.
 * No runtime imports, no agent imports, no sandbox imports.
 *
 * Ref: Phase P Batch 3 — Design System P.2
 */

export const colors = {
  light: {
    primary: "#1a56db",
    primaryHover: "#1e40af",
    secondary: "#6b7280",
    success: "#059669",
    warning: "#d97706",
    error: "#dc2626",
    info: "#2563eb",
    background: "#ffffff",
    surface: "#f9fafb",
    surfaceHover: "#f3f4f6",
    border: "#e5e7eb",
    text: "#111827",
    textSecondary: "#6b7280",
    textMuted: "#9ca3af",
    overlay: "rgba(0, 0, 0, 0.5)",
  },
  dark: {
    primary: "#3b82f6",
    primaryHover: "#60a5fa",
    secondary: "#9ca3af",
    success: "#10b981",
    warning: "#f59e0b",
    error: "#ef4444",
    info: "#60a5fa",
    background: "#111827",
    surface: "#1f2937",
    surfaceHover: "#374151",
    border: "#374151",
    text: "#f9fafb",
    textSecondary: "#9ca3af",
    textMuted: "#6b7280",
    overlay: "rgba(0, 0, 0, 0.7)",
  },
} as const;

export const spacing = {
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "32px",
  "2xl": "48px",
} as const;

export const borderRadius = {
  sm: "4px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  full: "9999px",
} as const;

export const typography = {
  fontFamily: {
    sans: "Inter, system-ui, -apple-system, sans-serif",
    mono: "JetBrains Mono, Fira Code, monospace",
  },
  fontSize: {
    xs: "12px",
    sm: "14px",
    base: "16px",
    lg: "18px",
    xl: "20px",
    "2xl": "24px",
    "3xl": "30px",
  },
  fontWeight: {
    normal: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
  },
} as const;

export const shadows = {
  sm: "0 1px 2px rgba(0, 0, 0, 0.05)",
  md: "0 4px 6px rgba(0, 0, 0, 0.1)",
  lg: "0 10px 15px rgba(0, 0, 0, 0.1)",
  xl: "0 20px 25px rgba(0, 0, 0, 0.15)",
} as const;

export const transitions = {
  fast: "150ms ease",
  normal: "250ms ease",
  slow: "350ms ease",
} as const;
