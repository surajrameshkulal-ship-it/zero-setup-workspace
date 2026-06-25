"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import clsx from "clsx";
import { Bot, GitBranch, LayoutDashboard, ListChecks, LogOut, ShieldAlert, ShieldCheck } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/repositories", label: "Repositories", icon: GitBranch },
  { href: "/scans", label: "Scans", icon: ListChecks },
  { href: "/rules", label: "Rules", icon: ShieldCheck },
  { href: "/engineering-requests", label: "Engineering", icon: Bot },
  { href: "/admin/dead-letter-scans", label: "Dead letters", icon: ShieldAlert }
];

export function AppShell({
  title,
  children,
  actions
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const pathname = usePathname();
  const { user, isLoading, signOut } = useAuth();

  if (isLoading) {
    return <main className="flex min-h-screen items-center justify-center bg-mist text-sm text-slate-500">Loading</main>;
  }

  return (
    <div className="min-h-screen bg-mist">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-panel lg:block">
        <div className="flex h-16 items-center gap-3 border-b border-line px-5">
          <Image src="/codedna-mark.svg" alt="" width={32} height={32} priority />
          <div>
            <div className="text-sm font-semibold text-ink">CodeDNA AI</div>
            <div className="text-xs text-slate-500">Governance</div>
          </div>
        </div>
        <nav className="space-y-1 p-3">
          {navigation.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "focus-ring flex items-center gap-3 rounded px-3 py-2 text-sm font-medium",
                  isActive ? "bg-brand text-white" : "text-slate-700 hover:bg-mist"
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-line bg-panel/95 backdrop-blur">
          <div className="flex min-h-16 items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold text-ink sm:text-xl">{title}</h1>
              {user ? <p className="truncate text-sm text-slate-500">{user.full_name}</p> : null}
            </div>
            <div className="flex flex-none items-center gap-2">
              {actions}
              <button
                type="button"
                className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
                onClick={signOut}
                title="Sign out"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto border-t border-line px-3 py-2 lg:hidden">
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "focus-ring inline-flex items-center gap-2 rounded px-3 py-2 text-sm font-medium",
                    isActive ? "bg-brand text-white" : "text-slate-700 hover:bg-mist"
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
