"use client";

import { useEffect, useState } from "react";
import { Joyride, STATUS, type EventData, type Step } from "react-joyride";
import type { UserRole } from "../contexts/RoleContext";

// Same localStorage naming convention as DemoDataManager
// (app/lib/completeDemoData.ts) -- the only other place this app
// persists anything client-side.
const seenKey = (role: UserRole) => `mediaudit_tour_seen_${role}`;

export function hasTourRun(role: UserRole): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(seenKey(role)) === "true";
  } catch {
    return true; // private browsing / storage disabled -- don't force a tour every load
  }
}

export function resetTour(role: UserRole) {
  try {
    localStorage.removeItem(seenKey(role));
  } catch {
    // ignore -- storage may be unavailable
  }
}

interface NavTourItem {
  href: string;
  label: string;
  tour: string;
}

interface ProductTourProps {
  navItems: NavTourItem[];
  role: UserRole | null;
}

export default function ProductTour({ navItems, role }: ProductTourProps) {
  const [run, setRun] = useState(false);

  useEffect(() => {
    if (!role) return;
    if (hasTourRun(role)) return;
    // Let the sidebar/topbar finish their first paint before Joyride
    // measures target positions -- avoids a mis-positioned first step.
    const timer = setTimeout(() => setRun(true), 400);
    return () => clearTimeout(timer);
  }, [role]);

  const steps: Step[] = [
    {
      target: '[data-tour="logo"]',
      title: "Welcome to MediAudit-X",
      content: "Quick 60-second tour of where everything lives -- skip any time.",
      placement: "right",
    },
    ...navItems.map((item): Step => ({
      target: `[data-tour="nav-${item.href}"]`,
      content: item.tour,
      placement: "right",
    })),
    {
      target: '[data-tour="search"]',
      content: "Search across claims, patients, and policy IDs from anywhere in the app.",
      placement: "bottom",
    },
    {
      target: '[data-tour="notifications"]',
      content: "Alerts for claim updates and anything that needs your attention.",
      placement: "bottom",
    },
    {
      target: '[data-tour="user-menu"]',
      content: "Your account and role -- switch back to the login screen from Logout in the sidebar.",
      placement: "bottom",
    },
  ];

  const handleEvent = (data: EventData) => {
    if (data.status === STATUS.FINISHED || data.status === STATUS.SKIPPED) {
      setRun(false);
      if (role) {
        try {
          localStorage.setItem(seenKey(role), "true");
        } catch {
          // ignore -- storage may be unavailable
        }
      }
    }
  };

  return (
    <Joyride
      steps={steps}
      run={run}
      continuous
      scrollToFirstStep
      onEvent={handleEvent}
      locale={{ last: "Done", skip: "Skip tour" }}
      options={{
        primaryColor: "#2563eb", // blue-600, matches the app's accent color
        zIndex: 10000,
        arrowColor: "#ffffff",
        backgroundColor: "#ffffff",
        textColor: "#0f172a", // slate-900
        buttons: ["back", "close", "skip", "primary"],
        overlayClickAction: false, // require Next/Skip -- an accidental backdrop click shouldn't dismiss
        skipBeacon: true, // show the tooltip immediately, no separate beacon-click step
        showProgress: true,
      }}
      styles={{
        tooltip: { borderRadius: 12 },
        buttonPrimary: { borderRadius: 8, backgroundColor: "#2563eb" },
        buttonBack: { color: "#64748b" }, // slate-500
      }}
    />
  );
}
