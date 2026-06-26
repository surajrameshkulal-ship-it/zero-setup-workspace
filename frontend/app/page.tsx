import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  GaugeCircle,
  GitPullRequest,
  ListChecks,
  LogIn,
  ScanSearch,
  ShieldCheck,
  Workflow
} from "lucide-react";

const features = [
  {
    icon: Bot,
    title: "AI code review",
    body: "Every pull request gets a structured, evidence-backed review summarizing risk, intent, and concrete remediation guidance."
  },
  {
    icon: ScanSearch,
    title: "Static analysis",
    body: "Semgrep runs on each change to surface security and quality findings before they ever reach your main branch."
  },
  {
    icon: GaugeCircle,
    title: "Risk scoring",
    body: "A consistent risk score across every scan turns a wall of findings into a clear, comparable signal for reviewers."
  },
  {
    icon: ShieldCheck,
    title: "Governance rules",
    body: "Organization-scoped rules and policies keep standards enforceable across teams, repositories, and reviewers."
  },
  {
    icon: ListChecks,
    title: "GitHub Check Runs",
    body: "Results land directly in the GitHub Checks tab, so developers stay in the workflow they already use every day."
  },
  {
    icon: Workflow,
    title: "Production hardened",
    body: "Idempotent webhooks, retry with backoff, a dead-letter queue, and health metrics keep the pipeline dependable at scale."
  }
];

const steps = [
  {
    label: "01",
    title: "Connect a repository",
    body: "Install the GitHub App and register the repositories you want under governance. Setup takes minutes."
  },
  {
    label: "02",
    title: "Open a pull request",
    body: "A webhook triggers a scan: Semgrep static analysis and an AI review run automatically against the diff."
  },
  {
    label: "03",
    title: "Review the evidence",
    body: "Risk score, findings, and the AI review appear in the GitHub Check Run and the CodeDNA dashboard."
  }
];

const stack = ["FastAPI", "PostgreSQL", "Redis", "Celery", "Semgrep", "Groq AI", "Next.js"];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-mist text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-panel/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Image src="/codedna-mark.svg" alt="" width={32} height={32} priority />
            <div className="leading-tight">
              <div className="text-sm font-semibold text-ink">CodeDNA AI</div>
              <div className="text-xs text-slate-500">Engineering governance</div>
            </div>
          </div>
          <nav className="flex items-center gap-2 sm:gap-3">
            <Link
              href="#features"
              className="focus-ring hidden rounded px-3 py-2 text-sm font-medium text-slate-700 hover:bg-mist sm:inline-flex"
            >
              Features
            </Link>
            <Link
              href="#how-it-works"
              className="focus-ring hidden rounded px-3 py-2 text-sm font-medium text-slate-700 hover:bg-mist sm:inline-flex"
            >
              How it works
            </Link>
            <Link
              href="/login"
              className="focus-ring inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-24">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs font-medium text-brand">
              <span className="h-1.5 w-1.5 rounded-full bg-signal" aria-hidden="true" />
              AI-powered PR governance
            </div>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl">
              Risk, rules, and review evidence in one operating view.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-600">
              CodeDNA AI reviews every pull request automatically — combining static analysis, AI review, and risk scoring
              into a single source of truth that lives right inside GitHub.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/login"
                className="focus-ring inline-flex items-center justify-center gap-2 rounded bg-brand px-5 py-3 text-sm font-semibold text-white hover:bg-brand-dark"
              >
                Open the dashboard
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href="#how-it-works"
                className="focus-ring inline-flex items-center justify-center gap-2 rounded border border-line bg-panel px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-mist"
              >
                See how it works
              </Link>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-6">
              <div>
                <dt className="text-2xl font-semibold text-ink">Every PR</dt>
                <dd className="mt-1 text-sm text-slate-500">scanned automatically</dd>
              </div>
              <div>
                <dt className="text-2xl font-semibold text-ink">2 engines</dt>
                <dd className="mt-1 text-sm text-slate-500">Semgrep + AI review</dd>
              </div>
              <div>
                <dt className="text-2xl font-semibold text-ink">1 view</dt>
                <dd className="mt-1 text-sm text-slate-500">in GitHub &amp; dashboard</dd>
              </div>
            </dl>
          </div>

          {/* Mock check-run card */}
          <div className="relative">
            <div className="rounded-xl border border-line bg-panel p-5 shadow-surface">
              <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
                <div className="flex items-center gap-2">
                  <GitPullRequest className="h-5 w-5 text-brand" aria-hidden="true" />
                  <span className="text-sm font-semibold text-ink">CodeDNA AI / review</span>
                </div>
                <span className="inline-flex rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                  medium risk
                </span>
              </div>
              <div className="space-y-3 py-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Risk score</span>
                  <span className="font-semibold text-ink">42 / 100</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-mist">
                  <div className="h-full w-[42%] rounded-full bg-[linear-gradient(90deg,#176b87,#d94f30)]" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Static findings</span>
                  <span className="font-medium text-ink">3 high · 5 medium</span>
                </div>
              </div>
              <div className="rounded-lg border border-line bg-mist p-3 text-sm leading-relaxed text-slate-700">
                <p className="font-medium text-ink">AI review summary</p>
                <p className="mt-1 text-slate-600">
                  Input validation is missing on the new endpoint, and a secret appears to be hard-coded. Recommend moving
                  the token to configuration and adding request schema validation before merge.
                </p>
              </div>
            </div>
            <div className="pointer-events-none absolute -right-6 -top-6 -z-10 h-40 w-40 rounded-full bg-brand/10 blur-2xl" />
            <div className="pointer-events-none absolute -bottom-8 -left-6 -z-10 h-40 w-40 rounded-full bg-signal/10 blur-2xl" />
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-y border-line bg-panel">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight text-ink">Governance that runs on every change</h2>
            <p className="mt-3 text-lg text-slate-600">
              Multiple engines working together so reviewers see one clear signal instead of scattered tools and noise.
            </p>
          </div>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <div key={feature.title} className="rounded-lg border border-line bg-mist p-5 shadow-surface">
                  <div className="flex h-10 w-10 items-center justify-center rounded border border-line bg-panel text-brand">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-ink">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{feature.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight text-ink">From pull request to evidence in three steps</h2>
          <p className="mt-3 text-lg text-slate-600">No new workflow to learn — CodeDNA AI meets your team inside GitHub.</p>
        </div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {steps.map((step) => (
            <div key={step.label} className="rounded-lg border border-line bg-panel p-6 shadow-surface">
              <div className="text-sm font-semibold text-signal">{step.label}</div>
              <h3 className="mt-2 text-lg font-semibold text-ink">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="px-4 pb-20 sm:px-6">
        <div className="mx-auto max-w-6xl overflow-hidden rounded-2xl bg-[linear-gradient(135deg,#17202a_0%,#176b87_55%,#d94f30_100%)] px-6 py-14 text-white sm:px-12">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold leading-tight sm:text-4xl">Bring governance to every pull request.</h2>
            <p className="mt-4 text-lg text-white/85">
              Sign in to explore the dashboard, review scan evidence, and see how CodeDNA AI keeps your codebase healthy.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/login"
                className="focus-ring inline-flex items-center justify-center gap-2 rounded bg-white px-5 py-3 text-sm font-semibold text-ink hover:bg-white/90"
              >
                Open the dashboard
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link
                href="#features"
                className="focus-ring inline-flex items-center justify-center gap-2 rounded border border-white/40 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10"
              >
                Explore features
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line bg-panel">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center gap-3">
            <Image src="/codedna-mark.svg" alt="" width={24} height={24} />
            <span className="text-sm font-medium text-ink">CodeDNA AI</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            {stack.map((tech, index) => (
              <span key={tech} className="flex items-center gap-2">
                {tech}
                {index < stack.length - 1 ? <span aria-hidden="true">·</span> : null}
              </span>
            ))}
          </div>
        </div>
      </footer>
    </main>
  );
}
