"use client";

import { useSyncExternalStore } from "react";

export type Breakpoint = "mobile" | "tablet" | "desktop";

const MOBILE_MAX = 767;
const TABLET_MAX = 1279;

function getBreakpoint(width: number): Breakpoint {
  if (width <= MOBILE_MAX) return "mobile";
  if (width <= TABLET_MAX) return "tablet";
  return "desktop";
}

function subscribe(callback: () => void) {
  window.addEventListener("resize", callback);
  return () => window.removeEventListener("resize", callback);
}

function getSnapshot(): Breakpoint {
  return getBreakpoint(window.innerWidth);
}

function getServerSnapshot(): Breakpoint {
  return "desktop";
}

export function useBreakpoint(): Breakpoint {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function useIsMobile(): boolean {
  const bp = useBreakpoint();
  return bp === "mobile";
}

export function useIsTabletOrBelow(): boolean {
  const bp = useBreakpoint();
  return bp === "mobile" || bp === "tablet";
}
