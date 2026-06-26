"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2, type LucideIcon } from "lucide-react";
import clsx from "clsx";

/* -------------------------------------------------------------------------- */
/* PageHeader                                                                  */
/* -------------------------------------------------------------------------- */

export function PageHeader({
  title,
  description,
  actions,
  className
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {description ? <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-none items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* SectionCard                                                                 */
/* -------------------------------------------------------------------------- */

export function SectionCard({
  title,
  description,
  actions,
  icon: Icon,
  children,
  bodyClassName,
  className
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  icon?: LucideIcon;
  children: ReactNode;
  bodyClassName?: string;
  className?: string;
}) {
  return (
    <section className={clsx("overflow-hidden rounded-xl border border-line bg-panel shadow-surface", className)}>
      {title || actions ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            {Icon ? (
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand ring-1 ring-brand/10">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
            ) : null}
            <div>
              {title ? <h3 className="text-sm font-semibold text-ink">{title}</h3> : null}
              {description ? <p className="text-xs text-slate-500">{description}</p> : null}
            </div>
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={clsx("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* ActionButton                                                                */
/* -------------------------------------------------------------------------- */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANT: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-dark shadow-surface",
  secondary: "border border-line bg-panel text-slate-700 hover:bg-mist",
  ghost: "text-slate-600 hover:bg-mist",
  danger: "border border-rose-200 bg-white text-rose-700 hover:bg-rose-50"
};

const SIZE: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm"
};

export function ActionButton({
  variant = "primary",
  size = "md",
  icon: Icon,
  loading = false,
  className,
  children,
  ...props
}: {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={clsx(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        VARIANT[variant],
        SIZE[size],
        className
      )}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : Icon ? (
        <Icon className="h-4 w-4" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/* DataTable                                                                   */
/* -------------------------------------------------------------------------- */

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
};

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  empty
}: {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T, index: number) => string;
  empty?: ReactNode;
}) {
  if (rows.length === 0 && empty) {
    return <>{empty}</>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  "sticky top-0 border-b border-line bg-mist px-4 py-2.5 text-xs font-semibold uppercase tracking-[0.06em] text-slate-500",
                  col.align === "right" && "text-right",
                  col.align === "center" && "text-center",
                  (!col.align || col.align === "left") && "text-left"
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={getRowKey(row, index)} className="transition-colors hover:bg-mist/60">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={clsx(
                    "border-b border-line px-4 py-3 text-slate-700",
                    col.align === "right" && "text-right",
                    col.align === "center" && "text-center",
                    col.className
                  )}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
