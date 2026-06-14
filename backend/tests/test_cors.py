# tests/test_cors.py — tests for the CORSMiddleware configuration in main.py.
#
# What is CORS?
#   Browsers enforce a "same-origin policy": a web page at http://localhost:5173
#   (React frontend) is BLOCKED from calling http://localhost:8000 (FastAPI backend)
#   unless the backend includes specific "Access-Control-*" headers in its response.
#   CORSMiddleware adds those headers automatically based on the settings in main.py.
#
# Development mode (APP_ENV=development): allow_origins=["*"] — any origin allowed.
# Production mode: allow_origins=[] (locked to specific Vercel URL — tested separately).

from fastapi.testclient import TestClient

# The React dev server always runs on this origin
FRONTEND_ORIGIN = "http://localhost:5173"


class TestCorsMiddlewareDevelopment:
    """Tests for CORSMiddleware in development mode (APP_ENV=development, allow_origins=['*'])."""

    def test_cors_header_present_on_get_with_origin(self, client: TestClient) -> None:
        """Verifies that a GET request with an Origin header receives Access-Control-Allow-Origin."""
        response = client.get("/health", headers={"Origin": FRONTEND_ORIGIN})

        assert "access-control-allow-origin" in response.headers

    def test_cors_allows_wildcard_in_development(self, client: TestClient) -> None:
        """Verifies that Access-Control-Allow-Origin is '*' in development mode."""
        response = client.get("/health", headers={"Origin": FRONTEND_ORIGIN})

        assert response.headers["access-control-allow-origin"] == "*"

    def test_cors_allows_arbitrary_origin_in_development(self, client: TestClient) -> None:
        """Verifies that development mode allows any Origin, not just localhost."""
        response = client.get(
            "/health", headers={"Origin": "https://some-other-site.example.com"}
        )

        assert response.headers.get("access-control-allow-origin") == "*"

    def test_cors_header_absent_without_origin_header(self, client: TestClient) -> None:
        """Verifies no CORS headers are added when the request lacks an Origin header.

        Server-to-server or direct curl calls don't send Origin — the middleware
        correctly omits CORS headers in that case (they serve no purpose there).
        """
        response = client.get("/health")

        assert "access-control-allow-origin" not in response.headers

    def test_cors_preflight_returns_200(self, client: TestClient) -> None:
        """Verifies that an OPTIONS preflight request returns 200 OK.

        Before a browser sends the real POST /chat request, it sends a 'preflight'
        OPTIONS request to check whether the server allows it. A 200 means 'yes'.
        """
        response = client.options(
            "/health",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200

    def test_cors_preflight_allows_content_type_header(self, client: TestClient) -> None:
        """Verifies that the preflight response lists Content-Type in allowed request headers.

        The React frontend sends Content-Type: application/json with POST /chat.
        The browser will block that request if Content-Type isn't in the allowed headers.
        """
        response = client.options(
            "/health",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        allowed_headers = response.headers.get("access-control-allow-headers", "").lower()

        assert "content-type" in allowed_headers

    def test_cors_preflight_allows_get_method(self, client: TestClient) -> None:
        """Verifies that GET is listed in the Access-Control-Allow-Methods response header."""
        response = client.options(
            "/health",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed_methods = response.headers.get("access-control-allow-methods", "")

        assert "GET" in allowed_methods

    def test_cors_preflight_allows_post_method(self, client: TestClient) -> None:
        """Verifies that POST is listed in the Access-Control-Allow-Methods response header.

        POST is required for /documents/upload and /chat.
        """
        response = client.options(
            "/health",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed_methods = response.headers.get("access-control-allow-methods", "")

        assert "POST" in allowed_methods
