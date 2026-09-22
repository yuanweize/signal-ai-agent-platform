"""
API Contract Drift and Real Integration Smoke Tests (Sections 3 & 4).
1. Validates that every frontend AI Studio client route and method exists in FastAPI OpenAPI schema.
2. Directly parses frontend/src/api.ts to verify no frontend path drifts from backend routes.
3. Real HTTP integration smoke against actual FastAPI app routes without mocking fetch.
"""

import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_admin
from app.database import get_session
from app.main import app
from app.schemas.auth import AdminUser


def test_openapi_contains_all_ai_studio_contracts():
    """Verify that backend OpenAPI schema exposes all expected AI Studio endpoints."""
    openapi = app.openapi()
    paths = openapi.get("paths", {})

    expected_contracts = [
        # AI Studio Overview
        ("GET", "/api/ai-studio/overview"),
        # Knowledge
        ("GET", "/api/ai-studio/knowledge/sources"),
        ("POST", "/api/ai-studio/knowledge/sources"),
        ("POST", "/api/ai-studio/knowledge/sources/{source_id}/documents"),
        ("DELETE", "/api/ai-studio/knowledge/sources/{source_id}"),
        ("DELETE", "/api/ai-studio/knowledge/documents/{document_id}"),
        ("POST", "/api/ai-studio/knowledge/documents/{document_id}/reindex"),
        ("GET", "/api/ai-studio/knowledge/search"),
        # Memory
        ("GET", "/api/ai-studio/memory"),
        ("POST", "/api/ai-studio/memory"),
        ("DELETE", "/api/ai-studio/memory/{memory_id}"),
        # Skills
        ("GET", "/api/ai-studio/skills"),
        ("PATCH", "/api/ai-studio/skills/{skill_name}"),
        # MCP
        ("GET", "/api/ai-studio/mcp/servers"),
        ("POST", "/api/ai-studio/mcp/servers/{server_id}/connect"),
        ("POST", "/api/ai-studio/mcp/servers/{server_id}/disconnect"),
        ("POST", "/api/ai-studio/mcp/servers/{server_id}/toggle"),
        # Learning
        ("GET", "/api/ai-studio/learning/candidates"),
        ("POST", "/api/ai-studio/learning/candidates/{candidate_id}/promote"),
        ("GET", "/api/ai-studio/learning/training-export"),
        # Evaluations
        ("POST", "/api/ai-studio/evals/run"),
        ("GET", "/api/ai-studio/evals/runs"),
        # Prompts
        ("GET", "/api/ai-studio/prompts/versions"),
        ("POST", "/api/ai-studio/prompts/versions/{version}/activate"),
        # Diagnostics
        ("GET", "/api/ai-studio/diagnostics"),
    ]

    missing = []
    for method, path in expected_contracts:
        if path not in paths:
            missing.append(f"Path missing: {method} {path}")
        elif method.lower() not in paths[path]:
            missing.append(f"Method missing: {method} {path} (has {list(paths[path].keys())})")

    assert not missing, "OpenAPI drift detected:\n" + "\n".join(missing)


def test_frontend_api_client_paths_match_backend_openapi():
    """Parse frontend/src/api.ts and ensure every AI Studio path exists in OpenAPI."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    frontend_api_path = repo_root / "frontend" / "src" / "api.ts"
    assert frontend_api_path.exists(), f"Could not find {frontend_api_path}"

    content = frontend_api_path.read_text(encoding="utf-8")
    # Match patterns like: this.request<...>(`/ai-studio/...` or '/ai-studio/...'
    # Normalize template literal expressions ${...} to {param}
    raw_matches = re.findall(
        r"request[<\w\s\[\]|:{},>?]*\(\s*[`'\"](/ai-studio/[^`'\"?]+)", content
    )

    openapi = app.openapi()
    openapi_paths = set(openapi.get("paths", {}).keys())

    # Build regex patterns for openapi paths
    def openapi_to_regex(p: str) -> re.Pattern:
        # e.g. /api/ai-studio/memory/{memory_id} -> ^/api/ai-studio/memory/[^/]+$
        pattern = re.sub(r"\{[^}]+\}", r"[^/]+", p)
        return re.compile(f"^{pattern}$")

    patterns = [openapi_to_regex(p) for p in openapi_paths]

    unmatched = []
    for raw in raw_matches:
        # Strip query string template variables e.g. ${qs}
        cleaned = re.sub(r"\$\{qs\}", "", raw).rstrip("?")
        # Normalize template literal parameter placeholders
        normalized = re.sub(r"\$\{[^}]+\}", "placeholder_param", cleaned)
        api_path = f"/api{normalized}"
        matched = any(pat.match(api_path) for pat in patterns)
        if not matched:
            unmatched.append(
                f"Frontend path {raw} (normalized as {api_path}) has no matching OpenAPI route"
            )

    assert not unmatched, "Frontend API client calls non-existent backend routes:\n" + "\n".join(
        unmatched
    )


@pytest.mark.asyncio
async def test_frontend_backend_integration_smoke(session):
    """Real HTTP integration smoke against actual FastAPI app routes without mocking fetch."""
    from sqlalchemy import text

    from app.services.migration import get_expected_alembic_head

    # Record migration version so readiness/features don't complain
    await session.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
    )
    await session.execute(
        text(
            f"INSERT OR REPLACE INTO alembic_version (version_num) VALUES ('{get_expected_alembic_head()}')"
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_admin] = lambda: AdminUser(username="smoke_admin")
    app.dependency_overrides[get_session] = lambda: session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-smoke-token"},
        ) as client:
            # 1. GET overview
            r_overview = await client.get("/api/ai-studio/overview")
            assert r_overview.status_code == 200, f"GET overview failed: {r_overview.text}"
            data_overview = r_overview.json()
            assert "total_ai_runs" in data_overview
            assert "automation_rate" in data_overview

            # 2. GET memory
            r_memory = await client.get("/api/ai-studio/memory")
            assert r_memory.status_code == 200, f"GET memory failed: {r_memory.text}"
            assert isinstance(r_memory.json(), list)

            # 3. PATCH skill
            r_skill = await client.patch(
                "/api/ai-studio/skills/catalog_query",
                json={"is_enabled": True},
            )
            # 200 if skill exists or 404 if not found, but route exists and returns JSON
            assert r_skill.status_code in (200, 404), f"PATCH skill failed: {r_skill.text}"

            # 4. GET MCP servers
            r_mcp = await client.get("/api/ai-studio/mcp/servers")
            assert r_mcp.status_code == 200, f"GET MCP servers failed: {r_mcp.text}"
            assert isinstance(r_mcp.json(), list)

            # 5. GET learning candidates
            r_candidates = await client.get("/api/ai-studio/learning/candidates")
            assert r_candidates.status_code == 200, f"GET candidates failed: {r_candidates.text}"
            assert isinstance(r_candidates.json(), list)

            # 6. POST evals/run
            r_evals = await client.post("/api/ai-studio/evals/run?limit=2")
            assert r_evals.status_code == 200, f"POST evals/run failed: {r_evals.text}"
            data_evals = r_evals.json()
            assert "pass_rate" in data_evals
            assert "total_cases" in data_evals

            # 7. GET prompts/versions
            r_prompts = await client.get("/api/ai-studio/prompts/versions")
            assert r_prompts.status_code == 200, f"GET prompts failed: {r_prompts.text}"
            assert isinstance(r_prompts.json(), list)

            # 8. GET diagnostics
            r_diag = await client.get("/api/ai-studio/diagnostics")
            assert r_diag.status_code == 200, f"GET diagnostics failed: {r_diag.text}"
            data_diag = r_diag.json()
            assert "llm" in data_diag
            assert "signal_gateway" in data_diag

    finally:
        app.dependency_overrides.clear()
