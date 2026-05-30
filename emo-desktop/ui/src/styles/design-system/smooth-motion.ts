/**
 * SmoothMotion — CSS transition presets for consistent animation.
 *
 * All animations are CSS-only (no framer-motion dependency).
 * Keeps motion subtle, fast, and non-distracting.
 */

export const transitions = {
  fast: "all 0.12s ease-out",
  normal: "all 0.2s ease-out",
  slow: "all 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
  spring: "all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
};

export const timing = {
  fast: 120,
  normal: 200,
  slow: 350,
};

/**
 * Apply smooth CSS transition to a React component style.
 */
export function smoothStyle(transition: keyof typeof transitions = "normal"): React.CSSProperties {
  return { transition: transitions[transition] };
}

/**
 * Fade-in animation keyframe name.
 * Usage: animation: `${fadeIn} 0.2s ease-out`;
 */
export const fadeIn = "smooth-fade-in";

export const slideUp = "smooth-slide-up";

export const scaleIn = "smooth-scale-in";

/**
 * Inject keyframes into document head (call once at app root).
 */
export function injectMotionKeyframes(): void {
  if (typeof document === "undefined") return; // SSR guard
  if (document.getElementById("smooth-motion-styles")) return;

  const style = document.createElement("style");
  style.id = "smooth-motion-styles";
  style.textContent = `
    @keyframes smooth-fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    @keyframes smooth-slide-up {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes smooth-scale-in {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }

    .smooth-enter {
      animation: smooth-slide-up 0.2s ease-out;
    }

    .smooth-fade {
      animation: smooth-fade-in 0.15s ease-out;
    }

    .smooth-scale {
      animation: smooth-scale-in 0.2s ease-out;
    }
  `;
  document.head.appendChild(style);
}
