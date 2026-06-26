"""Phase 11 inference hardening: infer the stack from all available evidence
(file tree, extensions, ecosystem manifests, source imports) — never returning
all-null runtime fields for a valid repository."""

from __future__ import annotations

from app.services.workspace.environment_spec_generator import EnvironmentSpecGenerator
from app.services.workspace.setup_intent_reader import SetupIntentReader
from app.services.workspace.workspace_builder import WorkspaceBuilder
from app.services.workspace.workspace_provisioner import WorkspaceProvisioner


def _intent(api_context, files: dict[str, str], file_tree=None) -> dict:
    return SetupIntentReader(api_context.db).build_intent(
        api_context.repository, files, dna=None, file_tree=file_tree
    )


def _spec_from(api_context, intent_fields: dict):
    """Persist the intent then build the env spec from it (full pipeline)."""
    from app.models.setup_intent import SetupIntent

    intent = SetupIntent(
        organization_id=api_context.organization.id, repository_id=api_context.repository.id
    )
    for k, v in intent_fields.items():
        setattr(intent, k, v)
    api_context.db.add(intent)
    api_context.db.flush()
    return EnvironmentSpecGenerator(api_context.db).build_spec(api_context.repository, intent, dna=None)


# -- static website (HTML/CSS/JS, no manifest) --------------------------------


def test_static_website_from_file_tree(api_context) -> None:
    files = {"index.html": "<!doctype html><html><body><h1>hi</h1></body></html>"}
    tree = ["index.html", "css/style.css", "js/app.js", "about.html"]
    intent = _intent(api_context, files, file_tree=tree)
    assert "HTML" in intent["languages"]
    assert "CSS" in intent["languages"]
    assert "JavaScript" in intent["languages"]
    assert "Static Website" in intent["frameworks"]
    assert intent["dev_command"]  # a static server plan exists
    assert intent["confidence_score"] > 0.0

    spec = _spec_from(api_context, intent)
    assert spec["primary_language"] in ("HTML", "JavaScript")
    assert spec["runtime_name"] == "Browser"
    assert spec["framework"] == "Static Website"
    assert spec["container_strategy"] != "unknown"
    assert spec["confidence_score"] > 0.0


# -- Go module (no package.json/requirements) ---------------------------------


def test_go_module_inference(api_context) -> None:
    files = {"go.mod": "module example.com/app\n\ngo 1.22\n\nrequire github.com/gin-gonic/gin v1.9.1\n"}
    tree = ["go.mod", "main.go", "internal/server/server.go"]
    intent = _intent(api_context, files, file_tree=tree)
    assert "Go" in intent["languages"]
    assert "Gin" in intent["frameworks"]
    assert intent["package_manager"] == "go modules"
    assert intent["runtime_version"] == "Go 1.22"
    assert intent["install_command"] == "go mod download"
    assert intent["test_command"] == "go test ./..."

    spec = _spec_from(api_context, intent)
    assert spec["primary_language"] == "Go"
    assert spec["runtime_name"] == "Go"
    assert spec["confidence_score"] > 0.0


# -- Rust crate ---------------------------------------------------------------


def test_rust_cargo_inference(api_context) -> None:
    files = {"Cargo.toml": '[package]\nname = "app"\nrust-version = "1.75"\n\n[dependencies]\naxum = "0.7"\n'}
    intent = _intent(api_context, files, file_tree=["Cargo.toml", "src/main.rs"])
    assert "Rust" in intent["languages"]
    assert "Axum" in intent["frameworks"]
    assert intent["package_manager"] == "cargo"
    assert intent["build_command"] == "cargo build"

    spec = _spec_from(api_context, intent)
    assert spec["primary_language"] == "Rust"
    assert spec["runtime_name"] == "Rust"


# -- extension-only Python repo (no manifest) ---------------------------------


def test_python_extension_only_repo(api_context) -> None:
    intent = _intent(api_context, {}, file_tree=["src/calc.py", "src/util.py", "tests/test_calc.py"])
    assert "Python" in intent["languages"]
    assert intent["confidence_score"] > 0.0

    spec = _spec_from(api_context, intent)
    # The key guarantee: a valid repository never yields all-null runtime fields.
    assert spec["primary_language"] == "Python"
    assert spec["runtime_name"] == "CPython"


# -- FastAPI inferred from source imports (manifest omits it) ------------------


def test_fastapi_from_source_imports(api_context) -> None:
    files = {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n"}
    intent = _intent(api_context, files, file_tree=["app/main.py", "app/routes.py"])
    assert "Python" in intent["languages"]
    assert "FastAPI" in intent["frameworks"]
    assert "uvicorn" in (intent["dev_command"] or "")

    spec = _spec_from(api_context, intent)
    assert spec["framework"] == "FastAPI"
    assert spec["runtime_name"] == "CPython"


# -- blueprint + provision produce meaningful, runtime-specific output --------


def test_static_site_flows_into_blueprint_and_provision(api_context) -> None:
    files = {"index.html": "<html></html>"}
    tree = ["index.html", "styles.css", "main.js"]
    SetupIntentReader(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
        files=files,
        file_tree=tree,
    )
    EnvironmentSpecGenerator(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    blueprint = WorkspaceBuilder(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert blueprint.runtime == "Browser"
    assert blueprint.readiness_score > 0

    plan = WorkspaceProvisioner(api_context.db).generate(
        repository_id=api_context.repository.id,
        organization_id=api_context.organization.id,
        actor_user_id=api_context.user.id,
    )
    assert plan.runtime == "Browser"
    assert plan.readiness_score > 0
    # The startup plan has a concrete prepare-application action, not a generic blank.
    app_phase = next(p for p in plan.startup_plan if p["phase"] == "Prepare application")
    assert any("http.server" in a for a in app_phase["actions"])
