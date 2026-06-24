import { AlertCircle, Loader2 } from "lucide-react";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-lg border border-line bg-panel text-sm text-slate-500">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex min-h-24 items-center rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <AlertCircle className="mr-2 h-4 w-4 flex-none" aria-hidden="true" />
      {message}
    </div>
  );
}

export function EmptyState({ title }: { title: string }) {
  return (
    <div className="flex min-h-28 items-center justify-center rounded-lg border border-dashed border-line bg-panel px-4 text-sm text-slate-500">
      {title}
    </div>
  );
}
