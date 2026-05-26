package openapi

import "testing"

func TestSpecContainsFoundationEndpoints(t *testing.T) {
	spec := Spec()

	if spec.OpenAPI != "3.1.0" {
		t.Fatalf("OpenAPI = %q, want 3.1.0", spec.OpenAPI)
	}
	if spec.Info.Title != "HotKey Server API" {
		t.Fatalf("title = %q, want HotKey Server API", spec.Info.Title)
	}
	if _, ok := spec.Paths["/healthz"]; !ok {
		t.Fatalf("paths missing /healthz")
	}
	if _, ok := spec.Paths["/openapi.json"]; !ok {
		t.Fatalf("paths missing /openapi.json")
	}
}
