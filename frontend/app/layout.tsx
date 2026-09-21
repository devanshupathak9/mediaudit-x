"use client";

import "./globals.css";
import AppShell from "./components/AppShell";
import { RoleProvider } from "./contexts/RoleContext";
import { useEffect } from "react";
import { DemoDataManager } from "./lib/completeDemoData";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  useEffect(() => {
    // Initialize demo data on app load
    DemoDataManager.initializeDemoData();
  }, []);

  return (
    // suppressHydrationWarning: browser extensions (e.g. Grammarly) add
    // attributes to <html>/<body> before React loads, which otherwise
    // triggers a hydration error.
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>MediAudit-X</title>
        <meta name="description" content="Clinical Claim Auditor & Temporal Drug-Interaction Engine" />
      </head>
      <body suppressHydrationWarning>
        <RoleProvider>
          <AppShell>{children}</AppShell>
        </RoleProvider>
      </body>
    </html>
  );
}
