# tests/test_health.py — tests for the GET /health liveness probe.
# Uses FastAPI's TestClient (no real server started — it simulates HTTP in-process).

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for GET /health — the app's liveness probe."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Verifies that GET /health returns HTTP 200 OK."""
        response = client.get("/health")

        assert response.status_code == 200

    def test_health_body_contains_status_ok(self, client: TestClient) -> None:
        """Verifies that GET /health body contains {"status": "ok"}."""
        response = client.get("/health")

        assert response.json()["status"] == "ok"

    def test_health_body_contains_version(self, client: TestClient) -> None:
        """Verifies that GET /health body includes a non-empty version string."""
        response = client.get("/health")
        data = response.json()

        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_version_matches_semver_format(self, client: TestClient) -> None:
        """Verifies that the version string follows MAJOR.MINOR.PATCH (semver) format."""
        response = client.get("/health")
        version = response.json()["version"]
        parts = version.split(".")

        assert len(parts) == 3, f"Expected semver X.Y.Z but got: {version}"
        assert all(part.isdigit() for part in parts), f"Non-numeric semver part in: {version}"

    def test_health_content_type_is_json(self, client: TestClient) -> None:
        """Verifies that GET /health responds with Content-Type: application/json."""
        response = client.get("/health")

        assert "application/json" in response.headers["content-type"]

    def test_health_returns_exactly_two_keys(self, client: TestClient) -> None:
        """Verifies that GET /health body has exactly the keys 'status' and 'version'."""
        response = client.get("/health")
        data = response.json()

        assert set(data.keys()) == {"status", "version"}
