package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestNewRouterUsesGinEngine(t *testing.T) {
	gin.SetMode(gin.TestMode)

	router := NewRouter()

	if router == nil {
		t.Fatalf("router is nil")
	}
	var _ *gin.Engine = router
}

func TestHealthEndpointReturnsServiceStatus(t *testing.T) {
	gin.SetMode(gin.TestMode)

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()

	NewRouter().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if body["status"] != "ok" {
		t.Fatalf("status body = %q, want ok", body["status"])
	}
	if body["service"] != "hotkey-server" {
		t.Fatalf("service body = %q, want hotkey-server", body["service"])
	}
}

func TestOpenAPIEndpointExportsJSONSpec(t *testing.T) {
	gin.SetMode(gin.TestMode)

	req := httptest.NewRequest(http.MethodGet, "/openapi.json", nil)
	rec := httptest.NewRecorder()

	NewRouter().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Content-Type"); !strings.HasPrefix(got, "application/json") {
		t.Fatalf("Content-Type = %q, want application/json", got)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode OpenAPI response: %v", err)
	}
	if body["openapi"] != "3.1.0" {
		t.Fatalf("openapi = %v, want 3.1.0", body["openapi"])
	}
	if _, ok := body["paths"].(map[string]any)["/healthz"]; !ok {
		t.Fatalf("OpenAPI paths missing /healthz")
	}
}
