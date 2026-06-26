"""Setup Intent Reader (Phase 11, Step 1).

Infers how a repository should be built and run by reading its manifest files
(README, package.json, lockfiles, requirements.txt, pyproject.toml, Dockerfile,
docker-compose.yml, Makefile, .github/workflows/*, .env.example, Procfile).

Read-only and deterministic-first: repository code is never executed, and only
environment variable *names* are captured (never values). Repository DNA is
reused as a baseline. AI is reserved for genuinely ambiguous cases and is
optional (skipped when unavailable).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import IntegrationError, NotFoundError
from app.integrations.github import GitHubIntegration
from app.models.github import GitHubInstallation
from app.models.repository import Repository
from app.models.setup_intent import SetupIntent
from app.services.audit_service import AuditService
from app.services.repository_dna_service import RepositoryDNAService

logger = logging.getLogger(__name__)

# Files to fetch for analysis.
MANIFEST_FILES = [
    "README.md",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "Gemfile.lock",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    ".env.example",
    "Procfile",
    "index.html",
    "runtime.txt",
    ".nvmrc",
    ".python-version",
    ".tool-versions",
]

# Lightweight source files probed (when present) to detect frameworks from
# imports when the manifest doesn't list them. Read-only; never executed.
SOURCE_PROBE_FILES = [
    "main.py",
    "app.py",
    "app/main.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "src/main.py",
    "server.js",
    "index.js",
    "app.js",
    "src/index.js",
    "src/index.ts",
    "main.go",
    "cmd/main.go",
]

# Map file extensions to languages so we can infer the stack from the repository
# file tree even when no manifest is present.
EXT_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
}
# Languages that are markup/styling rather than an application runtime.
NON_RUNTIME_LANGUAGES = {"HTML", "CSS"}
STATIC_SITE_FRAMEWORK = "Static Website"

# Priority for selecting the dominant runtime language.
LANGUAGE_PRIORITY = ["Python", "TypeScript", "JavaScript", "Go", "Rust", "Java", "Kotlin", "Ruby", "PHP"]

# Conventional commands for a language when no manifest declares them. This keeps
# an extension-only repository runnable-later (non-zero readiness) without
# inventing anything project-specific or executing code.
LANGUAGE_DEFAULTS = {
    "Python": {"pm": "pip", "install_command": "pip install -r requirements.txt", "test_command": "python -m pytest"},
    "Go": {"pm": "go modules", "install_command": "go mod download", "build_command": "go build ./...", "test_command": "go test ./...", "prod_command": "go run ."},
    "Rust": {"pm": "cargo", "install_command": "cargo fetch", "build_command": "cargo build", "test_command": "cargo test", "prod_command": "cargo run"},
    "JavaScript": {"pm": "npm", "install_command": "npm install"},
    "TypeScript": {"pm": "npm", "install_command": "npm install"},
    "Java": {"pm": "maven", "install_command": "mvn install -DskipTests", "build_command": "mvn package", "test_command": "mvn test"},
    "Ruby": {"pm": "bundler", "install_command": "bundle install"},
    "PHP": {"pm": "composer", "install_command": "composer install"},
}

JS_FRAMEWORKS = {
    "next": "Next.js",
    "nuxt": "Nuxt",
    "gatsby": "Gatsby",
    "@remix-run/react": "Remix",
    "@remix-run/node": "Remix",
    "react": "React",
    "vue": "Vue",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "vite": "Vite",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "koa": "Koa",
    "fastify": "Fastify",
    "@hapi/hapi": "hapi",
    "tailwindcss": "Tailwind CSS",
}
PY_FRAMEWORKS = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "starlette": "Starlette",
    "tornado": "Tornado",
    "sanic": "Sanic",
    "aiohttp": "aiohttp",
    "litestar": "Litestar",
}
DB_SIGNALS = {
    "postgres": "PostgreSQL",
    "psycopg": "PostgreSQL",
    "pg": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mongo": "MongoDB",
    "mongoose": "MongoDB",
    "pymongo": "MongoDB",
    "sqlite": "SQLite",
}
CACHE_SIGNALS = {"redis": "Redis", "memcached": "Memcached"}
QUEUE_SIGNALS = {"celery": "Celery", "rabbitmq": "RabbitMQ", "amqp": "RabbitMQ", "kafka": "Kafka", "bullmq": "BullMQ", "sidekiq": "Sidekiq"}
SERVICE_SIGNALS = {"stripe": "Stripe", "sendgrid": "SendGrid", "twilio": "Twilio", "boto3": "AWS", "aws-sdk": "AWS", "openai": "OpenAI", "groq": "Groq"}


class SetupIntentReader:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # -- queries ---------------------------------------------------------------

    def get_for_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent:
        intent = self._fetch(repository_id, organization_id)
        if not intent:
            raise NotFoundError("Setup intent not found")
        return intent

    def get_optional(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent | None:
        return self._fetch(repository_id, organization_id)

    def _fetch(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> SetupIntent | None:
        return self.db.scalar(
            select(SetupIntent).where(
                SetupIntent.repository_id == repository_id,
                SetupIntent.organization_id == organization_id,
            )
        )

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        repository_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        files: dict[str, str] | None = None,
        file_tree: list[str] | None = None,
        file_provider: Callable[[Repository], dict[str, str]] | None = None,
    ) -> SetupIntent:
        repository = self._require_repository(repository_id, organization_id)
        if files is None:
            provider = file_provider or GitHubManifestFileProvider(self.db)
            files = provider(repository)
            # Providers may also expose the full file tree for extension-based
            # inference; tolerate providers (e.g. test fakes) that don't.
            if file_tree is None:
                file_tree = getattr(provider, "tree", None)
        dna = RepositoryDNAService(self.db).get_optional(repository_id, organization_id)

        fields = self.build_intent(repository, files, dna, file_tree=file_tree)

        intent = self.db.scalar(select(SetupIntent).where(SetupIntent.repository_id == repository.id))
        if intent is None:
            intent = SetupIntent(organization_id=organization_id, repository_id=repository.id)
            self.db.add(intent)
        for key, value in fields.items():
            setattr(intent, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="setup_intent_generated",
            target_type="repository",
            target_id=str(repository.id),
            metadata={"confidence": fields.get("confidence_score"), "sources": fields.get("sources_analyzed")},
        )
        self.db.commit()
        self.db.refresh(intent)
        return intent

    # -- inference -------------------------------------------------------------

    def build_intent(
        self,
        repository: Repository,
        files: dict[str, str],
        dna: Any | None,
        file_tree: list[str] | None = None,
    ) -> dict:
        by_name = {k.split("/")[-1].lower(): v for k, v in files.items()}
        all_text = "\n".join(files.values())

        # The file tree (all repository paths) drives extension-based inference.
        # Fall back to the analyzed files plus any DNA-observed important files.
        tree = list(file_tree or [])
        if not tree:
            tree = list(files.keys()) + list(getattr(dna, "important_files", None) or [])

        languages: set[str] = set(getattr(dna, "languages", None) or [])
        frameworks: set[str] = set(getattr(dna, "frameworks", None) or [])
        databases: set[str] = set(getattr(dna, "databases", None) or [])
        caches: set[str] = set()
        queues: set[str] = set(getattr(dna, "queues", None) or [])
        services: set[str] = set()
        env_vars: set[str] = set()
        ports: set[int] = set()
        commands: dict[str, str | None] = {
            "install_command": None, "dev_command": None, "prod_command": None,
            "test_command": None, "build_command": None, "lint_command": None,
        }
        package_manager: str | None = None
        runtime_version: str | None = None

        # package.json
        pkg = self._parse_json(by_name.get("package.json"))
        if pkg is not None:
            languages.add("JavaScript")
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for dep in deps:
                if dep in JS_FRAMEWORKS:
                    frameworks.add(JS_FRAMEWORKS[dep])
                self._classify_dep(dep, databases, caches, queues, services)
                if "typescript" in dep:
                    languages.add("TypeScript")
            scripts = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}
            commands["dev_command"] = self._npm(scripts, ["dev", "develop", "start:dev"])
            commands["prod_command"] = self._npm(scripts, ["start", "serve"])
            commands["build_command"] = self._npm(scripts, ["build"])
            commands["test_command"] = self._npm(scripts, ["test"])
            commands["lint_command"] = self._npm(scripts, ["lint"])
            engines = pkg.get("engines", {})
            if isinstance(engines, dict) and engines.get("node"):
                runtime_version = f"Node {engines['node']}"

        # package manager from lockfiles
        if "pnpm-lock.yaml" in by_name:
            package_manager = "pnpm"
        elif "yarn.lock" in by_name:
            package_manager = "yarn"
        elif "package-lock.json" in by_name or pkg is not None:
            package_manager = package_manager or "npm"

        # Python: requirements.txt / pyproject.toml
        req = by_name.get("requirements.txt")
        pyproject = by_name.get("pyproject.toml")
        py_deps_text = ""
        if req is not None:
            languages.add("Python")
            py_deps_text += req
        if pyproject is not None:
            languages.add("Python")
            py_deps_text += "\n" + pyproject
            requires = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', pyproject)
            if requires:
                runtime_version = runtime_version or f"Python {requires.group(1)}"
            if "[tool.poetry]" in pyproject:
                package_manager = package_manager or "poetry"
        if py_deps_text:
            lowered = py_deps_text.lower()
            for key, label in PY_FRAMEWORKS.items():
                if key in lowered:
                    frameworks.add(label)
            self._classify_text(lowered, databases, caches, queues, services)
            package_manager = package_manager or "pip"
            if "pytest" in lowered:
                commands["test_command"] = commands["test_command"] or "python -m pytest"
            if "fastapi" in lowered:
                commands["dev_command"] = commands["dev_command"] or "uvicorn app.main:app --reload"
                commands["prod_command"] = commands["prod_command"] or "uvicorn app.main:app --host 0.0.0.0 --port 8000"
            if "django" in lowered:
                commands["dev_command"] = commands["dev_command"] or "python manage.py runserver"
            commands["install_command"] = commands["install_command"] or (
                "pip install -e ." if pyproject is not None else "pip install -r requirements.txt"
            )

        # default install for JS
        if pkg is not None:
            commands["install_command"] = commands["install_command"] or f"{package_manager or 'npm'} install"

        # Dockerfile
        dockerfile = by_name.get("dockerfile")
        docker_files: list[str] = []
        if dockerfile is not None:
            docker_files.append("Dockerfile")
            for m in re.finditer(r"(?im)^\s*EXPOSE\s+(\d+)", dockerfile):
                ports.add(int(m.group(1)))
            base = re.search(r"(?im)^\s*FROM\s+([^\s]+)", dockerfile)
            if base:
                inferred = self._runtime_from_image(base.group(1))
                if inferred and not runtime_version:
                    runtime_version = inferred
                if inferred:
                    if inferred.startswith("Python"):
                        languages.add("Python")
                    elif inferred.startswith("Node"):
                        languages.add("JavaScript")

        # docker-compose
        compose = by_name.get("docker-compose.yml") or by_name.get("docker-compose.yaml")
        if compose is not None:
            docker_files.append("docker-compose")
            lowered = compose.lower()
            self._classify_text(lowered, databases, caches, queues, services)
            for m in re.finditer(r"(\d{2,5}):(\d{2,5})", compose):
                ports.add(int(m.group(2)))

        # Makefile targets
        makefile = by_name.get("makefile")
        if makefile is not None:
            targets = set(re.findall(r"(?im)^([a-zA-Z0-9_-]+):", makefile))
            for target, slot in (("install", "install_command"), ("test", "test_command"),
                                  ("build", "build_command"), ("lint", "lint_command"),
                                  ("run", "prod_command"), ("dev", "dev_command")):
                if target in targets and not commands[slot]:
                    commands[slot] = f"make {target}"

        # Procfile
        procfile = by_name.get("procfile")
        if procfile is not None:
            web = re.search(r"(?im)^web:\s*(.+)$", procfile)
            if web and not commands["prod_command"]:
                commands["prod_command"] = web.group(1).strip()

        # .env.example -> variable names only
        env_example = by_name.get(".env.example")
        if env_example is not None:
            for line in env_example.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                line = line[len("export "):].strip() if line.lower().startswith("export ") else line
                if "=" in line:
                    name = line.split("=", 1)[0].strip()
                    if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        env_vars.add(name)

        # CI/CD provider
        cicd_provider = None
        if any(k.startswith(".github/workflows/") for k in files):
            cicd_provider = "GitHub Actions"
        elif ".gitlab-ci.yml" in by_name:
            cicd_provider = "GitLab CI"
        elif by_name.get("dockerfile") and "circleci" in all_text.lower():
            cicd_provider = "CircleCI"

        # Go (go.mod)
        gomod = by_name.get("go.mod")
        if gomod is not None:
            languages.add("Go")
            package_manager = package_manager or "go modules"
            gv = re.search(r"(?im)^go\s+([0-9.]+)", gomod)
            if gv and not runtime_version:
                runtime_version = f"Go {gv.group(1)}"
            commands["install_command"] = commands["install_command"] or "go mod download"
            commands["build_command"] = commands["build_command"] or "go build ./..."
            commands["test_command"] = commands["test_command"] or "go test ./..."
            commands["prod_command"] = commands["prod_command"] or "go run ."
            self._classify_text(gomod.lower(), databases, caches, queues, services)
            if "gin-gonic/gin" in gomod:
                frameworks.add("Gin")
            if "labstack/echo" in gomod:
                frameworks.add("Echo")
            if "gofiber/fiber" in gomod:
                frameworks.add("Fiber")

        # Rust (Cargo.toml)
        cargo = by_name.get("cargo.toml")
        if cargo is not None:
            languages.add("Rust")
            package_manager = package_manager or "cargo"
            rv = re.search(r'(?im)^\s*rust-version\s*=\s*["\']([^"\']+)["\']', cargo)
            if rv and not runtime_version:
                runtime_version = f"Rust {rv.group(1)}"
            commands["install_command"] = commands["install_command"] or "cargo fetch"
            commands["build_command"] = commands["build_command"] or "cargo build"
            commands["test_command"] = commands["test_command"] or "cargo test"
            commands["prod_command"] = commands["prod_command"] or "cargo run"
            if "actix-web" in cargo:
                frameworks.add("Actix Web")
            if "axum" in cargo:
                frameworks.add("Axum")
            if "rocket" in cargo:
                frameworks.add("Rocket")

        # Java/Kotlin (pom.xml / build.gradle)
        pom = by_name.get("pom.xml")
        gradle = by_name.get("build.gradle") or by_name.get("build.gradle.kts")
        if pom is not None or gradle is not None:
            languages.add("Java")
            java_text = (pom or "") + "\n" + (gradle or "")
            if pom is not None:
                package_manager = package_manager or "maven"
                commands["install_command"] = commands["install_command"] or "mvn install -DskipTests"
                commands["build_command"] = commands["build_command"] or "mvn package"
                commands["test_command"] = commands["test_command"] or "mvn test"
            else:
                package_manager = package_manager or "gradle"
                commands["install_command"] = commands["install_command"] or "gradle dependencies"
                commands["build_command"] = commands["build_command"] or "gradle build"
                commands["test_command"] = commands["test_command"] or "gradle test"
            if "spring-boot" in java_text or "springframework" in java_text:
                frameworks.add("Spring Boot")
                commands["prod_command"] = commands["prod_command"] or "java -jar target/app.jar"
            self._classify_text(java_text.lower(), databases, caches, queues, services)

        # PHP (composer.json)
        composer = self._parse_json(by_name.get("composer.json"))
        if composer is not None:
            languages.add("PHP")
            package_manager = package_manager or "composer"
            commands["install_command"] = commands["install_command"] or "composer install"
            deps = {**composer.get("require", {}), **composer.get("require-dev", {})}
            joined = " ".join(deps.keys()).lower()
            if "laravel/framework" in joined:
                frameworks.add("Laravel")
                commands["dev_command"] = commands["dev_command"] or "php artisan serve"
            if "symfony/" in joined:
                frameworks.add("Symfony")
            self._classify_text(joined, databases, caches, queues, services)

        # Ruby (Gemfile)
        gemfile = by_name.get("gemfile")
        if gemfile is not None:
            languages.add("Ruby")
            package_manager = package_manager or "bundler"
            commands["install_command"] = commands["install_command"] or "bundle install"
            lowered = gemfile.lower()
            if "rails" in lowered:
                frameworks.add("Ruby on Rails")
                commands["dev_command"] = commands["dev_command"] or "bin/rails server"
            if "sinatra" in lowered:
                frameworks.add("Sinatra")
            if "rspec" in lowered:
                commands["test_command"] = commands["test_command"] or "bundle exec rspec"
            self._classify_text(lowered, databases, caches, queues, services)

        # Pipfile / setup.py (additional Python signals)
        if by_name.get("pipfile") is not None or by_name.get("setup.py") is not None or by_name.get("setup.cfg") is not None:
            languages.add("Python")
            package_manager = package_manager or ("pipenv" if by_name.get("pipfile") else "pip")
            commands["install_command"] = commands["install_command"] or (
                "pipenv install" if by_name.get("pipfile") else "pip install -e ."
            )

        # Runtime version files
        if by_name.get(".nvmrc") and not runtime_version:
            runtime_version = f"Node {by_name['.nvmrc'].strip()}"
        if by_name.get(".python-version") and not runtime_version:
            runtime_version = f"Python {by_name['.python-version'].strip()}"
        if by_name.get("runtime.txt") and not runtime_version:
            rt = by_name["runtime.txt"].strip()
            m_rt = re.search(r"(python|node|ruby|go)[-/ ]?([0-9.]+)", rt, re.IGNORECASE)
            if m_rt:
                runtime_version = f"{m_rt.group(1).title()} {m_rt.group(2)}"

        # GitHub Actions workflow commands (CI is an authoritative source for the
        # real install/test/build commands a project uses).
        ci_text = "\n".join(v for k, v in files.items() if k.startswith(".github/workflows/"))
        if ci_text:
            self._commands_from_ci(ci_text, commands)

        # README commands/frameworks (lowest-priority textual fallback).
        readme = by_name.get("readme.md") or by_name.get("readme")
        if readme:
            self._commands_from_readme(readme, commands)
            self._frameworks_from_text(readme, frameworks, languages)

        # Framework inference from source imports (when manifests omit them)
        self._scan_source_imports(files, frameworks, languages, commands)

        # Extension-based language inference from the repository file tree. This
        # is the fallback that ensures a valid repository is never classified as
        # entirely unknown even when no manifest is present.
        ext_languages = self._languages_from_tree(tree)
        languages |= ext_languages

        # Static website detection: HTML present, no application backend/manifest.
        has_backend_manifest = any(
            by_name.get(n) is not None
            for n in (
                "package.json", "requirements.txt", "pyproject.toml", "pipfile", "setup.py",
                "go.mod", "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts",
                "composer.json", "gemfile",
            )
        )
        has_index_html = "index.html" in {p.split("/")[-1].lower() for p in tree} or by_name.get("index.html") is not None
        if has_index_html and not has_backend_manifest:
            frameworks.add(STATIC_SITE_FRAMEWORK)
            languages.add("HTML")
            commands["dev_command"] = commands["dev_command"] or "python3 -m http.server 8000"
            commands["prod_command"] = commands["prod_command"] or "python3 -m http.server 8000"
            if 8000 not in ports:
                ports.add(8000)

        # Language defaults: ensure a repo detected only from extensions/structure
        # still has conventional, runnable-later commands (non-zero readiness).
        runtime_langs = [lang for lang in languages if lang not in NON_RUNTIME_LANGUAGES]
        primary_lang = next((lang for lang in LANGUAGE_PRIORITY if lang in runtime_langs), None)
        if primary_lang and not package_manager and not commands["install_command"]:
            defaults = LANGUAGE_DEFAULTS.get(primary_lang)
            if defaults:
                package_manager = package_manager or defaults.get("pm")
                for slot in ("install_command", "build_command", "test_command", "prod_command"):
                    if not commands[slot] and defaults.get(slot):
                        commands[slot] = defaults[slot]

        # Health check endpoint
        health = None
        m = re.search(r"(/health[a-z]*|/healthz|/livez|/readyz)", all_text)
        if m:
            health = m.group(1)

        fields = {
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "package_manager": package_manager,
            "runtime_version": runtime_version,
            **commands,
            "env_vars": sorted(env_vars),
            "ports": sorted(ports),
            "databases": sorted(databases),
            "caches": sorted(caches),
            "queues": sorted(queues),
            "external_services": sorted(services),
            "docker": {"present": bool(docker_files), "files": docker_files},
            "cicd_provider": cicd_provider,
            "health_check_endpoint": health,
            "sources_analyzed": sorted(files.keys()),
            "notes": self._notes(files),
        }
        fields["confidence_score"] = self._confidence(fields)
        fields["evidence"] = self._build_evidence(fields, by_name, files, tree, dna)
        return fields

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _npm(scripts: dict, names: list[str]) -> str | None:
        for name in names:
            if name in scripts:
                return f"npm run {name}" if name not in ("start",) else "npm start"
        return None

    # Command patterns recognised in READMEs and CI workflows.
    _CMD_PATTERNS = [
        ("install_command", re.compile(r"\b((?:npm ci)|(?:npm install)|(?:pnpm install)|(?:yarn install)|(?:yarn)|(?:pip install -r requirements\.txt)|(?:pip install -e \.)|(?:poetry install)|(?:bundle install)|(?:go mod download)|(?:cargo fetch)|(?:composer install))\b", re.IGNORECASE)),
        ("test_command", re.compile(r"\b((?:npm (?:run )?test)|(?:pnpm test)|(?:yarn test)|(?:python -m pytest)|(?:pytest)|(?:go test \./\.\.\.)|(?:cargo test)|(?:bundle exec rspec)|(?:mvn test))\b", re.IGNORECASE)),
        ("build_command", re.compile(r"\b((?:npm run build)|(?:pnpm build)|(?:yarn build)|(?:go build \./\.\.\.)|(?:cargo build)|(?:mvn package)|(?:make build))\b", re.IGNORECASE)),
        ("lint_command", re.compile(r"\b((?:npm run lint)|(?:eslint \.)|(?:ruff check \.?)|(?:flake8))\b", re.IGNORECASE)),
        ("dev_command", re.compile(r"\b((?:npm run dev)|(?:uvicorn [\w.:]+(?: --reload)?)|(?:flask run)|(?:python manage\.py runserver)|(?:rails server))\b", re.IGNORECASE)),
        ("prod_command", re.compile(r"\b((?:npm start)|(?:gunicorn [\w.:]+)|(?:node [\w./-]+\.js))\b", re.IGNORECASE)),
    ]

    @classmethod
    def _commands_from_ci(cls, ci_text: str, commands: dict[str, str | None]) -> None:
        run_lines = "\n".join(re.findall(r"(?im)^\s*(?:-\s*)?run:\s*(.+)$", ci_text)) or ci_text
        cls._fill_commands_from_text(run_lines, commands)

    @classmethod
    def _commands_from_readme(cls, readme: str, commands: dict[str, str | None]) -> None:
        cls._fill_commands_from_text(readme, commands)

    @classmethod
    def _fill_commands_from_text(cls, text: str, commands: dict[str, str | None]) -> None:
        for slot, pattern in cls._CMD_PATTERNS:
            if commands.get(slot):
                continue
            m = pattern.search(text)
            if m:
                commands[slot] = m.group(1).strip()

    # Curated, low-false-positive framework names for README text matching.
    _README_FRAMEWORKS = {
        "next.js": ("Next.js", "JavaScript"),
        "nuxt": ("Nuxt", "JavaScript"),
        "gatsby": ("Gatsby", "JavaScript"),
        "remix": ("Remix", "JavaScript"),
        "sveltekit": ("SvelteKit", "JavaScript"),
        "express": ("Express", "JavaScript"),
        "nestjs": ("NestJS", "JavaScript"),
        "nest.js": ("NestJS", "JavaScript"),
        "fastify": ("Fastify", "JavaScript"),
        "vite": ("Vite", "JavaScript"),
        "fastapi": ("FastAPI", "Python"),
        "django": ("Django", "Python"),
        "flask": ("Flask", "Python"),
        "starlette": ("Starlette", "Python"),
        "tornado": ("Tornado", "Python"),
        "sanic": ("Sanic", "Python"),
        "spring boot": ("Spring Boot", "Java"),
        "laravel": ("Laravel", "PHP"),
        "ruby on rails": ("Ruby on Rails", "Ruby"),
    }

    @classmethod
    def _frameworks_from_text(cls, text: str, frameworks: set[str], languages: set[str]) -> None:
        low = text.lower()
        for needle, (label, language) in cls._README_FRAMEWORKS.items():
            if needle in low:
                frameworks.add(label)
                languages.add(language)

    @staticmethod
    def _languages_from_tree(tree: list[str]) -> set[str]:
        """Infer languages from file extensions across the repository tree."""
        skip = ("node_modules/", "vendor/", "dist/", "build/", ".venv/", "site-packages/", ".git/")
        langs: set[str] = set()
        for path in tree:
            low = path.lower()
            if any(seg in low for seg in skip):
                continue
            dot = low.rfind(".")
            if dot == -1:
                continue
            lang = EXT_LANGUAGE.get(low[dot:])
            if lang:
                langs.add(lang)
        return langs

    @staticmethod
    def _scan_source_imports(
        files: dict[str, str], frameworks: set[str], languages: set[str], commands: dict[str, str | None]
    ) -> None:
        """Detect frameworks from imports in a few well-known entrypoint files."""
        for path in SOURCE_PROBE_FILES:
            text = files.get(path)
            if not text:
                continue
            low = text.lower()
            if path.endswith(".py"):
                languages.add("Python")
                if "fastapi" in low:
                    frameworks.add("FastAPI")
                    commands["dev_command"] = commands["dev_command"] or "uvicorn app.main:app --reload"
                    commands["prod_command"] = (
                        commands["prod_command"] or "uvicorn app.main:app --host 0.0.0.0 --port 8000"
                    )
                if "flask" in low:
                    frameworks.add("Flask")
                if "django" in low:
                    frameworks.add("Django")
                if "starlette" in low:
                    frameworks.add("Starlette")
            elif path.endswith(".ts"):
                languages.add("TypeScript")
                SetupIntentReader._scan_js_frameworks(low, frameworks)
            elif path.endswith(".js"):
                languages.add("JavaScript")
                SetupIntentReader._scan_js_frameworks(low, frameworks)
            elif path.endswith(".go"):
                languages.add("Go")

    @staticmethod
    def _scan_js_frameworks(low: str, frameworks: set[str]) -> None:
        if "express" in low:
            frameworks.add("Express")
        if "next/" in low or "from 'next'" in low or 'from "next"' in low:
            frameworks.add("Next.js")
        if "@nestjs" in low:
            frameworks.add("NestJS")
        if "fastify" in low:
            frameworks.add("Fastify")

    @staticmethod
    def _classify_dep(dep: str, databases, caches, queues, services) -> None:
        SetupIntentReader._classify_text(dep.lower(), databases, caches, queues, services)

    @staticmethod
    def _classify_text(text: str, databases, caches, queues, services) -> None:
        for key, label in DB_SIGNALS.items():
            if key in text:
                databases.add(label)
        for key, label in CACHE_SIGNALS.items():
            if key in text:
                caches.add(label)
        for key, label in QUEUE_SIGNALS.items():
            if key in text:
                queues.add(label)
        for key, label in SERVICE_SIGNALS.items():
            if key in text:
                services.add(label)

    @staticmethod
    def _runtime_from_image(image: str) -> str | None:
        image = image.lower()
        m = re.search(r"python:([0-9.]+)", image)
        if m:
            return f"Python {m.group(1)}"
        m = re.search(r"node:([0-9.]+)", image)
        if m:
            return f"Node {m.group(1)}"
        return None

    @staticmethod
    def _parse_json(text: str | None) -> dict | None:
        if not text:
            return None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _notes(files: dict[str, str]) -> list[str]:
        present = {k.split("/")[-1].lower() for k in files}
        missing = [name for name in MANIFEST_FILES if name.lower() not in present]
        if not files:
            return ["No manifest files were available for analysis."]
        notes = [f"Analyzed {len(files)} manifest file(s); inference is read-only and code was never executed."]
        if missing:
            notes.append("Optional manifests not present: " + ", ".join(missing) + ".")
        return notes

    @staticmethod
    def _confidence(fields: dict) -> float:
        signals = [
            bool(fields["languages"]),
            bool(fields["package_manager"]),
            bool(fields["install_command"]),
            bool(fields["dev_command"] or fields["prod_command"]),
            bool(fields["build_command"] or fields["test_command"]),
            bool(fields["frameworks"]),
        ]
        return round(sum(signals) / len(signals), 2)

    # -- evidence --------------------------------------------------------------

    @staticmethod
    def _build_evidence(fields: dict, by_name: dict, files: dict, tree: list[str], dna: Any | None) -> list[dict]:
        """Explain why each inferred value was chosen, citing the source."""
        ev: list[dict] = []

        def add(field: str, value, source: str, detail: str) -> None:
            if value in (None, "", [], {}):
                return
            ev.append({"field": field, "value": value, "source": source, "detail": detail})

        # Source for each language.
        lang_source = {
            "JavaScript": "package.json" if "package.json" in by_name else "file extensions",
            "TypeScript": "package.json" if "package.json" in by_name else "file extensions (.ts)",
            "Python": next(
                (s for s in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py") if s.lower() in by_name),
                "Dockerfile" if "dockerfile" in by_name else "file extensions (.py)",
            ),
            "Go": "go.mod" if "go.mod" in by_name else "file extensions (.go)",
            "Rust": "Cargo.toml" if "cargo.toml" in by_name else "file extensions (.rs)",
            "Java": "pom.xml" if "pom.xml" in by_name else ("build.gradle" if ("build.gradle" in by_name or "build.gradle.kts" in by_name) else "file extensions"),
            "PHP": "composer.json" if "composer.json" in by_name else "file extensions (.php)",
            "Ruby": "Gemfile" if "gemfile" in by_name else "file extensions (.rb)",
            "HTML": "index.html" if "index.html" in by_name else "file extensions (.html)",
            "CSS": "file extensions (.css)",
        }
        dna_langs = set(getattr(dna, "languages", None) or [])
        for lang in fields["languages"]:
            source = "Repository DNA" if lang in dna_langs and lang not in by_name else lang_source.get(lang, "repository structure")
            add("primary_language", lang, source, f"Detected {lang} from {source}.")

        # Package manager.
        pm = fields["package_manager"]
        if pm:
            pm_source = {
                "pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "npm": "package.json / package-lock.json",
                "poetry": "pyproject.toml ([tool.poetry])", "pip": "requirements.txt / pyproject.toml",
                "pipenv": "Pipfile", "go modules": "go.mod", "cargo": "Cargo.toml",
                "maven": "pom.xml", "gradle": "build.gradle", "composer": "composer.json", "bundler": "Gemfile",
            }.get(pm, "manifest")
            add("package_manager", pm, pm_source, f"Package manager {pm} inferred from {pm_source}.")

        # Runtime version.
        rv = fields["runtime_version"]
        if rv:
            if "engines" in (by_name.get("package.json") or ""):
                rv_source = "package.json (engines)"
            elif "requires-python" in (by_name.get("pyproject.toml") or ""):
                rv_source = "pyproject.toml (requires-python)"
            elif "dockerfile" in by_name and ("python:" in by_name["dockerfile"].lower() or "node:" in by_name["dockerfile"].lower()):
                rv_source = "Dockerfile (FROM image)"
            elif "go.mod" in by_name:
                rv_source = "go.mod"
            else:
                rv_source = "runtime version file"
            add("runtime_version", rv, rv_source, f"Runtime version {rv} from {rv_source}.")

        # Frameworks.
        for fw in fields["frameworks"]:
            add("framework", fw, "manifest/imports/README", f"Framework {fw} detected from dependencies, source imports, or README.")

        # Commands.
        cmd_sources = []
        if "package.json" in by_name:
            cmd_sources.append("package.json scripts")
        if "makefile" in by_name:
            cmd_sources.append("Makefile")
        if "procfile" in by_name:
            cmd_sources.append("Procfile")
        if "dockerfile" in by_name:
            cmd_sources.append("Dockerfile")
        if any(k.startswith(".github/workflows/") for k in files):
            cmd_sources.append("GitHub Actions workflow")
        if "readme.md" in by_name:
            cmd_sources.append("README.md")
        cmd_source = ", ".join(cmd_sources) or "language defaults"
        for slot, label in (
            ("install_command", "install"), ("build_command", "build"),
            ("test_command", "test"), ("dev_command", "dev/start"), ("prod_command", "start"),
        ):
            if fields.get(slot):
                add(slot, fields[slot], cmd_source, f"{label} command inferred from {cmd_source}.")

        # Services + ports.
        compose_present = "docker-compose.yml" in by_name or "docker-compose.yaml" in by_name
        svc_source = "docker-compose.yml" if compose_present else "dependency manifests"
        for svc in fields["databases"] + fields["caches"] + fields["queues"]:
            add("services", svc, svc_source, f"Service {svc} detected from {svc_source}.")
        if fields["ports"]:
            port_source = "Dockerfile (EXPOSE)" if "dockerfile" in by_name else ("docker-compose.yml" if compose_present else "framework default")
            add("ports", fields["ports"], port_source, f"Ports {fields['ports']} from {port_source}.")

        return ev

    def _require_repository(self, repository_id: uuid.UUID, organization_id: uuid.UUID) -> Repository:
        repository = self.db.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.organization_id == organization_id,
            )
        )
        if not repository:
            raise NotFoundError("Repository not found")
        return repository


class GitHubManifestFileProvider:
    """Fetches the manifest files (and workflow files) read-only via the App token."""

    def __init__(self, db: Session, *, integration: GitHubIntegration | None = None) -> None:
        self.db = db
        self.gh = integration or GitHubIntegration()
        self.tree: list[str] = []

    def __call__(self, repository: Repository) -> dict[str, str]:
        # Fatal: the repository must be connected to a GitHub installation.
        if repository.github_installation_id is None:
            raise IntegrationError("Repository is not connected to a GitHub installation.")
        installation = self.db.get(GitHubInstallation, repository.github_installation_id)
        if installation is None:
            raise IntegrationError("GitHub installation is missing for this repository.")

        # Fatal: token retrieval (invalid App credentials/installation) propagates.
        token = self.gh.get_installation_token(installation.installation_id)
        ref = repository.default_branch or "main"

        # Fatal: one repo-level call distinguishes "repo inaccessible" from
        # "file missing". If we can read the default branch, per-file 404s are
        # simply optional manifests that don't exist.
        try:
            self.gh.get_branch_sha(token=token, owner=repository.owner, repo=repository.name, branch=ref)
        except IntegrationError as exc:
            raise IntegrationError(
                f"Unable to access repository '{repository.full_name}' on GitHub. "
                "Check that the GitHub App is installed and has repository read access."
            ) from exc

        files: dict[str, str] = {}
        for path in MANIFEST_FILES + SOURCE_PROBE_FILES:
            content = self._safe_get(token, repository, path, ref)
            if content is not None:
                files[path] = content
        # Workflow listing already tolerates a missing directory.
        for workflow_path in self.gh.list_directory(
            token=token, owner=repository.owner, repo=repository.name, path=".github/workflows", ref=ref
        ):
            content = self._safe_get(token, repository, workflow_path, ref)
            if content is not None:
                files[workflow_path] = content

        # Full file tree drives extension-based language inference. Tolerate
        # integrations (e.g. test fakes) that don't implement tree listing.
        tree_fn = getattr(self.gh, "list_repository_tree", None)
        if callable(tree_fn):
            try:
                self.tree = tree_fn(token=token, owner=repository.owner, repo=repository.name, ref=ref) or []
            except IntegrationError:
                self.tree = []
        return files

    def _safe_get(self, token: str, repository: Repository, path: str, ref: str) -> str | None:
        """Fetch one optional manifest; a 404 (missing file) is not fatal."""
        try:
            return self.gh.get_file_content(
                token=token, owner=repository.owner, repo=repository.name, path=path, ref=ref
            )
        except IntegrationError:
            logger.info("setup_intent_manifest_missing", extra={"repository": repository.full_name, "path": path})
            return None
