"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import {
  Bot,
  Brain,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  LogOut,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon
} from "lucide-react";
import type { User } from "@/types/api";

type NavItem = { href: string; label: string; icon: LucideIcon };
type NavGroup = { label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }]
  },
  {
    label: "Governance",
    items: [
      { href: "/repositories", label: "Repositories", icon: GitBranch },
      { href: "/scans", label: "Scans", icon: ListChecks },
      { href: "/rules", label: "Rules", icon: ShieldCheck }
    ]
  },
  {
    label: "AI engineering",
    items: [{ href: "/engineering-requests", label: "Engineering", icon: Bot }]
  },
  {
    label: "Brain",
    items: [{ href: "/product-brain", label: "Product Brain", icon: Brain }]
  },
  {
    label: "Operations",
    items: [{ href: "/admin/dead-letter-scans", label: "Dead letters", icon: ShieldAlert }]
  }
];

function initials(name?: string | null): string {
  if (!name) return "··";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "··";
}

export function Sidebar({
  user,
  onSignOut,
  onNavigate
}: {
  user: User | null;
  onSignOut: () => void;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="flex h-16 items-center gap-3 border-b border-line px-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft ring-1 ring-brand/15">
          <Image src="/codedna-mark.svg" alt="" width={22} height={22} priority />
        </span>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight text-ink">CodeDNA AI</div>
          <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">Governance</div>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={isActive ? "page" : undefined}
                    className={clsx(
                      "focus-ring group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-soft text-brand-ink"
                        : "text-slate-600 hover:bg-mist hover:text-ink"
                    )}
                  >
                    {isActive ? (
                      <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand" aria-hidden="true" />
                    ) : null}
                    <Icon
                      className={clsx("h-4 w-4 flex-none", isActive ? "text-brand" : "text-slate-400 group-hover:text-slate-600")}
                      aria-hidden="true"
                    />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-brand text-xs font-semibold text-white">
            {initials(user?.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-ink">{user?.full_name ?? "Signed in"}</div>
            <div className="truncate text-xs text-slate-500">{user?.email ?? ""}</div>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            title="Sign out"
            className="focus-ring inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg border border-line text-slate-500 hover:bg-mist hover:text-ink"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
