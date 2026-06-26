"use client";

import { useState, type ReactNode } from "react";
import { X } from "lucide-react";
import clsx from "clsx";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { useAuth } from "@/hooks/use-auth";

export function AppShell({
  title,
  description,
  children,
  actions
}: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const { user, isLoading, signOut } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-mist text-sm text-slate-500">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
          Loading workspace
        </span>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-mist">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line lg:block">
        <Sidebar user={user} onSignOut={signOut} />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85%] border-r border-line shadow-lifted">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="focus-ring absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-panel text-slate-500 hover:bg-mist"
              aria-label="Close menu"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
            <Sidebar user={user} onSignOut={signOut} onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className={clsx("lg:pl-64")}>
        <Topbar title={title} description={description} actions={actions} onMenu={() => setDrawerOpen(true)} />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
