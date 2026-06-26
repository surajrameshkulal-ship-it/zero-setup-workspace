"use client";

import type { ReactNode } from "react";
import { Menu } from "lucide-react";

export function Topbar({
  title,
  description,
  actions,
  onMenu
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  onMenu?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-panel/80 backdrop-blur supports-[backdrop-filter]:bg-panel/70">
      <div className="flex min-h-16 items-center gap-3 px-4 py-3 sm:px-6">
        <button
          type="button"
          onClick={onMenu}
          className="focus-ring inline-flex h-9 w-9 flex-none items-center justify-center rounded-lg border border-line text-slate-600 hover:bg-mist lg:hidden"
          title="Open menu"
          aria-label="Open navigation menu"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold tracking-tight text-ink sm:text-xl">{title}</h1>
          {description ? <p className="truncate text-sm text-slate-500">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-none items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
