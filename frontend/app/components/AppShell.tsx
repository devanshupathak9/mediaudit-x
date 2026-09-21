"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  LayoutDashboard,
  FileStack,
  ShieldCheck,
  Search,
  Bell,
  ChevronDown,
  MessageSquare,
  ClipboardList,
  Building2,
  UserCircle,
  Upload,
  LogOut,
  Info,
} from "lucide-react";
import { useRole } from "../contexts/RoleContext";
import ProductTour from "./ProductTour";

// Hospital navigation - LIMITED ACCESS
// `tour` is the one-line description ProductTour shows when spotlighting
// this item -- kept here, next to the item it describes, rather than in
// a separate lookup table that could drift out of sync.
const HOSPITAL_NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, tour: "Your at-a-glance view of claim volume and status." },
  { href: "/claims", label: "My Claims", icon: FileStack, tour: "Every claim your hospital has submitted, with live status." },
  { href: "/hospital/create-claim", label: "Create Claim", icon: Upload, tour: "Upload documents and submit a new claim for review." },
  { href: "/about", label: "About", icon: Info, tour: "What MediAudit-X is and how it fits into your workflow." },
];

// Insurance reviewer navigation - READ ONLY for claims
const INSURANCE_NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, tour: "Your at-a-glance view of claim volume and status." },
  { href: "/review-queue", label: "Review Queue", icon: ClipboardList, tour: "Claims waiting on your decision, AI-adjudicated and ready to review." },
  { href: "/audit-trail", label: "Audit History", icon: ShieldCheck, tour: "The hash-chained, tamper-evident record of every decision." },
  { href: "/about", label: "About", icon: Info, tour: "What MediAudit-X is and how it fits into your workflow." },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { role, logout, userName, userTitle, isAuthenticated } = useRole();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthenticated && !pathname.startsWith("/login")) {
      router.push("/login");
    }
  }, [isAuthenticated, pathname, router]);

  // Handle logout
  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  // Render login page without shell
  if (pathname.startsWith("/login")) {
    return <>{children}</>;
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return null; // Show nothing while redirecting
  }

  const NAV_ITEMS = role === "hospital" ? HOSPITAL_NAV : INSURANCE_NAV;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <ProductTour navItems={NAV_ITEMS} role={role} />

      {/* Sidebar */}
      <aside className="flex w-60 flex-col bg-navy-950 text-slate-300">
        <div data-tour="logo" className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            M
          </div>
          <span className="text-base font-semibold text-white">MediAudit-X</span>
        </div>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                data-tour={`nav-${href}`}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150 ${
                  active
                    ? "bg-blue-600/15 text-white ring-1 ring-inset ring-blue-500/30"
                    : "text-slate-400 hover:translate-x-0.5 hover:bg-white/5 hover:text-slate-100"
                }`}
              >
                <Icon size={17} strokeWidth={2} />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Role and User Info */}
        <div className="border-t border-white/10 mx-3 mb-3 pt-3">
          <div className="flex items-center gap-2 mb-2">
            {role === "hospital" ? (
              <Building2 size={14} className="text-slate-400" />
            ) : (
              <UserCircle size={14} className="text-slate-400" />
            )}
            <div className="text-xs text-slate-400">
              {role === "hospital" ? "Hospital Portal" : "Insurance Reviewer"}
            </div>
          </div>
          <div className="text-sm font-medium text-slate-200">{userName}</div>
          <div className="text-xs text-slate-400 mt-0.5">{userTitle}</div>

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            className="mt-3 w-full rounded-md bg-red-500/10 px-2 py-1.5 text-xs text-red-300 hover:bg-red-500/20 transition-colors flex items-center justify-center gap-2"
          >
            <LogOut size={12} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-h-screen flex-1 flex-col">
        {/* Topbar */}
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <div data-tour="search" className="relative w-full max-w-md">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search claims, patients, or policy ID..."
              className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-700 placeholder:text-slate-400 transition-shadow focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
          <div className="flex items-center gap-4">
            <button data-tour="notifications" className="relative rounded-full p-2 text-slate-500 transition-colors hover:bg-slate-100">
              <Bell size={18} />
              <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-red-500" />
            </button>
            <div data-tour="user-menu" className="flex items-center gap-2 pl-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-xs font-semibold text-white">
                {role === "hospital" ? "CC" : "SM"}
              </div>
              <div className="leading-tight">
                <div className="text-sm font-medium text-slate-800">{userName}</div>
                <div className="text-xs text-slate-400">{userTitle}</div>
              </div>
              <ChevronDown size={14} className="text-slate-400" />
            </div>
          </div>
        </header>

        <main key={pathname} className="flex-1 animate-fade-in px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
