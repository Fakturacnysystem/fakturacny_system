import type { Transition, Variants } from "motion/react";

export const motionDurations = {
  instant: 0.12,
  fast: 0.18,
  standard: 0.26,
  emphasis: 0.42,
} as const;

export const motionSprings = {
  snappy: {
    type: "spring",
    stiffness: 420,
    damping: 32,
    mass: 0.78,
  },
  smooth: {
    type: "spring",
    stiffness: 220,
    damping: 28,
    mass: 0.95,
  },
} satisfies Record<string, Transition>;

export const motionEase = [0.22, 1, 0.36, 1] as const;

export const fadeUp = {
  initial: { opacity: 0, y: 18, filter: "blur(10px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -12, filter: "blur(8px)" },
} as const;

export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
} as const;

export const staggerContainer = (stagger = 0.06, delayChildren = 0) => ({
  initial: {},
  animate: {
    transition: {
      staggerChildren: stagger,
      delayChildren,
    },
  },
}) satisfies Variants;

export const staggerItem = {
  initial: { opacity: 0, y: 14 },
  animate: {
    opacity: 1,
    y: 0,
    transition: motionSprings.smooth,
  },
} satisfies Variants;

export const panelTransition: Transition = {
  ...motionSprings.smooth,
};

export const tabTransition: Transition = {
  duration: motionDurations.fast,
  ease: motionEase,
};

export const overlayTransition: Transition = {
  duration: motionDurations.standard,
  ease: motionEase,
};
