import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertCircle, Inbox, Loader2, RefreshCw } from "lucide-react";
import clsx from "clsx";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex min-h-40 items-center justify-center rounded-xl border border-line bg-panel text-sm text-slate-500 shadow-surface"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="mr-2 h-4 w-4 animate-spin text-brand" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded bg-line/70", className)} aria-hidden="true" />;
}

/** A table-shaped placeholder used while tabular data loads. */
export function TableSkeleton({ rows = 5, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div
      className="rounded-xl border border-line bg-panel p-4 shadow-surface"
      role="status"
      aria-live="polite"
      aria-label="Loading"
    >
      <div className="space-y-3">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }).map((_, index) => (
            <Skeleton key={`head-${index}`} className="h-3" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div
            key={`row-${rowIndex}`}
            className="grid gap-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: columns }).map((_, colIndex) => (
              <Skeleton key={`cell-${rowIndex}-${colIndex}`} className="h-4" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** A grid of card-shaped placeholders used while summary cards load. */
export function CardsSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" role="status" aria-live="polite" aria-label="Loading">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-xl border border-line bg-panel p-5 shadow-surface">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-8 w-16" />
          <Skeleton className="mt-2 h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 shadow-surface" role="alert">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
        <div className="flex-1">
          <p className="font-medium">Something went wrong</p>
          <p className="mt-1 text-rose-700">{message}</p>
        </div>
      </div>
      {onRetry ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={onRetry}
            className="focus-ring inline-flex items-center gap-2 rounded border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-100"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line bg-panel px-6 py-12 text-center shadow-surface">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-brand ring-1 ring-brand/10">
        <Icon className="h-6 w-6" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        {description ? <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{description}</p> : null}
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
