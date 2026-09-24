"""
Tests for CORS PATCH support and header exposure.
Verifies Section 15 requirements:
- OPTIONS preflight with Access-Control-Request-Method: PATCH
- Access-Control-Allow-Methods contains PATCH
- Access-Control-Expose-Headers contains X-Total-Count
- Restrictive origin verification (not wildcard)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cors_options_preflight_patch_allowed():
    """Verify CORS preflight allows PATCH for allowed origins."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Preflight to skills endpoint
        response = await client.options(
            "/api/ai-studio/skills/customer-support",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert response.status_code == 200
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allowed_methods, f"PATCH not in allowed methods: {allowed_methods}"
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

        # Preflight to products endpoint
        response_prod = await client.options(
            "/api/products/1",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert response_prod.status_code == 200
        allowed_methods_prod = response_prod.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allowed_methods_prod


@pytest.mark.asyncio
async def test_cors_exposes_x_total_count_header():
    """Verify CORS configuration exposes X-Total-Count header for pagination."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/ai-studio/runs",
            headers={
                "Origin": "http://localhost:3000",
            },
        )
        exposed_headers = response.headers.get("access-control-expose-headers", "")
        assert "X-Total-Count" in exposed_headers, f"X-Total-Count not exposed: {exposed_headers}"
