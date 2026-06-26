"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Bot, GitBranch, LogIn, ShieldCheck } from "lucide-react";
import { ActionButton } from "@/components/ui";
import { login } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

const HIGHLIGHTS = [
  { icon: ShieldCheck, title: "Policy-grade reviews", body: "Risk scoring, company rules, and architecture checks on every pull request." },
  { icon: Bot, title: "AI engineering, human-gated", body: "Plan, generate, and validate changes that only ever land as a draft PR." },
  { icon: GitBranch, title: "Zero-setup workspaces", body: "Detect the stack and prepare a reproducible workspace from any repository." }
];

export default function LoginPage() {
  const router = useRouter();
  const { user, signIn } = useAuth({ requireAuth: false });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      router.replace("/dashboard");
    }
  }, [router, user]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await login(email, password);
      signIn(response.access_token, response.user);
      router.replace("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-mist lg:grid-cols-[1.05fr_0.95fr]">
      <section className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-soft ring-1 ring-brand/15">
              <Image src="/codedna-mark.svg" alt="" width={26} height={26} priority />
            </span>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-ink">CodeDNA AI</h1>
              <p className="text-sm text-slate-500">Engineering governance platform</p>
            </div>
          </div>

          <div className="rounded-2xl border border-line bg-panel p-6 shadow-card sm:p-8">
            <h2 className="text-lg font-semibold text-ink">Sign in</h2>
            <p className="mt-1 text-sm text-slate-500">Welcome back. Enter your credentials to continue.</p>
            <form className="mt-6 space-y-4" onSubmit={onSubmit}>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="email">Email</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  className="focus-ring w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink placeholder:text-slate-400"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className="focus-ring w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink placeholder:text-slate-400"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </div>
              {error ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>
              ) : null}
              <ActionButton type="submit" icon={LogIn} loading={isSubmitting} className="w-full">
                {isSubmitting ? "Signing in" : "Sign in"}
              </ActionButton>
            </form>
          </div>
          <p className="mt-6 text-center text-xs text-slate-400">
            Secured access · human-in-the-loop AI · audit-logged actions
          </p>
        </div>
      </section>

      <section className="relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between bg-[radial-gradient(120%_120%_at_0%_0%,#4f46e5_0%,#3730a3_45%,#0f172a_100%)] p-10 text-white">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" /> AI PR governance
        </div>
        <div>
          <p className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
            Risk, rules, and review evidence in one operating view.
          </p>
          <p className="mt-3 max-w-md text-sm text-white/70">
            CodeDNA brings engineering governance, AI-assisted changes, and zero-setup workspaces into a single,
            auditable platform.
          </p>
          <div className="mt-8 space-y-4">
            {HIGHLIGHTS.map((h) => {
              const Icon = h.icon;
              return (
                <div key={h.title} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div>
                    <div className="text-sm font-semibold">{h.title}</div>
                    <div className="text-sm text-white/65">{h.body}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="text-xs text-white/50">© CodeDNA AI · Research preview</div>
      </section>
    </main>
  );
}
