"""Smoke tests for all routes - verify they return 200."""

import pytest


class TestPublicRoutes:
    """Test that all public GET routes return 200."""

    # Routes that need no parameters
    SIMPLE_ROUTES = [
        ("/", "dashboard"),
        ("/species", "species list"),
        ("/files", "files list"),
        ("/tasks", "tasks list"),
        ("/tasks/api", "tasks API"),
        ("/settings", "settings"),
        ("/labeling", "labeling interface"),
        ("/labeling/stats", "labeling stats"),
    ]

    @pytest.mark.parametrize("route,description", SIMPLE_ROUTES)
    def test_simple_routes(self, client, route, description):
        """Test that simple routes return 200."""
        response = client.get(route)
        assert response.status_code == 200, (
            f"{description} ({route}) returned {response.status_code}"
        )

    def test_api_hourly_activity(self, client):
        """Test hourly activity API endpoint."""
        response = client.get("/api/stats/hourly-activity")
        assert response.status_code == 200
        assert response.content_type == "application/json"


class TestRouteDiscovery:
    """Auto-discover and test all GET routes."""

    # Routes to skip (require specific IDs, auth, or have side effects)
    SKIP_PATTERNS = [
        "/data/",  # Static file serving
        "/thumbnail/",  # Requires valid detection ID
        "/metrics",  # Prometheus metrics
        "/set-language",  # Redirects
        "<",  # Routes with parameters
    ]

    def test_discover_all_get_routes(self, client):
        """Discover all GET routes and verify they're tested."""
        from birdhomie.app import app

        untested_routes = []

        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods:
                continue

            route = rule.rule

            # Skip routes with parameters or in skip list
            if any(pattern in route for pattern in self.SKIP_PATTERNS):
                continue

            # Check if route is covered by our explicit tests
            simple_routes = [r[0] for r in TestPublicRoutes.SIMPLE_ROUTES]
            if route not in simple_routes and route != "/api/stats/hourly-activity":
                untested_routes.append(route)

        # This test documents untested routes - not a failure, just info
        if untested_routes:
            print(f"\nRoutes not covered by smoke tests: {untested_routes}")


class TestParameterizedRoutes:
    """Test routes that require parameters."""

    def test_species_detail_exists(self, client):
        """Test species detail page with a known taxon."""
        # First get a valid taxon_id from the species list
        response = client.get("/species")
        assert response.status_code == 200

        # Try to access a species detail (taxon_id from test data)
        # This might 404 if no species exist, which is acceptable
        response = client.get("/species/13094")
        assert response.status_code in [200, 404]

    def test_species_detail_not_found(self, client):
        """Test species detail returns 404 for invalid ID."""
        response = client.get("/species/999999999")
        assert response.status_code == 404

    def test_visit_detail_not_found(self, client):
        """Test visit detail returns 404 for invalid ID."""
        response = client.get("/visits/999999999")
        assert response.status_code == 404

    def test_file_detail_not_found(self, client):
        """Test file detail returns 404 for invalid ID."""
        response = client.get("/files/999999999")
        assert response.status_code == 404

    def test_reprocess_file_not_found(self, client):
        """Test reprocess returns redirect with flash for invalid ID."""
        response = client.post("/files/999999999/reprocess", follow_redirects=False)
        # Should redirect to files list with error flash
        assert response.status_code == 302


class TestAPIEndpoints:
    """Test API endpoints return valid JSON."""

    def test_tasks_api_returns_json(self, client):
        """Test tasks API returns valid JSON array."""
        response = client.get("/tasks/api")
        assert response.status_code == 200
        assert response.content_type == "application/json"
        data = response.get_json()
        assert isinstance(data, list)

    def test_hourly_activity_returns_json(self, client):
        """Test hourly activity API returns expected structure."""
        response = client.get("/api/stats/hourly-activity")
        assert response.status_code == 200
        data = response.get_json()
        assert "labels" in data
        assert "data" in data
        assert len(data["labels"]) == 24  # 24 hours

    @pytest.mark.parametrize("period", ["today", "week", "month"])
    def test_hourly_activity_periods(self, client, period):
        """Test hourly activity API with different periods."""
        response = client.get(f"/api/stats/hourly-activity?period={period}")
        assert response.status_code == 200
