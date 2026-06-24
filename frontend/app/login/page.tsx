"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { LogIn } from "lucide-react";
import { login } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

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
    <main className="grid min-h-screen bg-mist lg:grid-cols-[0.9fr_1.1fr]">
      <section className="flex items-center justify-center border-r border-line bg-panel px-6 py-10">
        <form className="w-full max-w-md space-y-5" onSubmit={onSubmit}>
          <div className="flex items-center gap-3">
            <Image src="/codedna-mark.svg" alt="" width={42} height={42} priority />
            <div>
              <h1 className="text-2xl font-semibold text-ink">CodeDNA AI</h1>
              <p className="text-sm text-slate-500">Engineering governance</p>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              className="focus-ring w-full rounded border border-line bg-white px-3 py-2 text-sm"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="focus-ring w-full rounded border border-line bg-white px-3 py-2 text-sm"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          {error ? <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div> : null}
          <button
            type="submit"
            className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded bg-brand px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#125870] disabled:cursor-not-allowed disabled:opacity-70"
            disabled={isSubmitting}
          >
            <LogIn className="h-4 w-4" aria-hidden="true" />
            {isSubmitting ? "Signing in" : "Sign in"}
          </button>
        </form>
      </section>
      <section className="hidden bg-[linear-gradient(135deg,#17202a_0%,#176b87_55%,#d94f30_100%)] p-8 lg:flex lg:items-end">
        <div className="max-w-xl text-white">
          <div className="mb-4 inline-flex rounded border border-white/30 px-3 py-1 text-sm">AI PR Governance</div>
          <p className="text-4xl font-semibold leading-tight">Risk, rules, and review evidence in one operating view.</p>
        </div>
      </section>
    </main>
  );
}
