# EMO AI — Design System

## Philosophy
Linear/Raycast-inspired glass morphism design. Subtle, fast, non-distracting.
Every component is CSS-only with zero external animation dependencies.

## Core Components

### Glass Panel (`glass-panel.css`)
| Class | Purpose |
|-------|---------|
| `.glass-panel` | Frosted glass card (light mode) |
| `.glass-panel-dark` | Frosted glass card (dark mode) |
| `.glass-input` | Glass-textured input field |
| `.metric-card` | Compact stat display card |
| `.section-header` | Uppercase section label |
| `.live-dot` | Pulsing green connection indicator |

### Status Badge (`status-badge.tsx`)
States: `active`, `degraded`, `down`, `rate_limited`, `pending`, `running`, `completed`, `failed`, `skipped`
```tsx
<StatusBadge state="active" />
<StatusBadge state="failed" label="Custom Label" size="sm" />
```

### Smooth Motion (`smooth-motion.ts`)
| Token | Value | Use |
|-------|-------|-----|
| `transitions.fast` | 0.12s ease-out | Hover states |
| `transitions.normal` | 0.2s ease-out | Panel transitions |
| `transitions.slow` | 0.35s cubic-bezier | Modal entrances |
| `transitions.spring` | 0.4s cubic-bezier | Celebratory animations |

CSS classes: `.smooth-enter`, `.smooth-fade`, `.smooth-scale`

### Timeline Node (`timeline-node.tsx`)
```tsx
<TimelineNode label="Plan Execution" state="running" durationMs={1200} />
<ExecutionTimeline>{children}</ExecutionTimeline>
```

### Status Badge Usage Guidelines
- Use `size="sm"` inside TimelineNodes and compact cards
- Use default `size="md"` in tables and list views
- Always pair with a visual indicator (colored dot or icon)

## Color Palette
| Token | Light | Dark |
|-------|-------|------|
| Background | `#f5f5f7` | `#121218` |
| Surface | `rgba(255,255,255,0.6)` | `rgba(18,18,24,0.75)` |
| Primary | `#2563eb` | `#60a5fa` |
| Success | `#16a34a` | `#4ade80` |
| Warning | `#ca8a04` | `#fbbf24` |
| Error | `#dc2626` | `#f87171` |
| Text Primary | `#111827` | `#f3f4f6` |
| Text Secondary | `#6b7280` | `#9ca3af` |

## Spacing
- Card padding: 16px
- Section gap: 20px
- Element gap: 8-12px
- Border radius: 8-12px

## Usage
```tsx
import { injectMotionKeyframes } from "./styles/design-system/smooth-motion";
import { StatusBadge } from "./styles/design-system/status-badge";
import "./styles/design-system/glass-panel.css";

// At app root:
useEffect(() => { injectMotionKeyframes(); }, []);
```
