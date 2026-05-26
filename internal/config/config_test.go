package config

import "testing"

func TestLoadReturnsGoRebuildDefaults(t *testing.T) {
	t.Setenv("HOTKEY_HTTP_ADDR", "")
	t.Setenv("HOTKEY_DATABASE_URL", "")
	t.Setenv("HOTKEY_REDIS_URL", "")

	cfg := Load()

	if cfg.HTTPAddr != ":8080" {
		t.Fatalf("HTTPAddr = %q, want :8080", cfg.HTTPAddr)
	}
	if cfg.DatabaseURL != "postgres://hotkey:hotkey@localhost:5432/hotkey?sslmode=disable" {
		t.Fatalf("DatabaseURL = %q", cfg.DatabaseURL)
	}
	if cfg.RedisURL != "redis://localhost:6379/0" {
		t.Fatalf("RedisURL = %q", cfg.RedisURL)
	}
}

func TestLoadAllowsEnvironmentOverrides(t *testing.T) {
	t.Setenv("HOTKEY_HTTP_ADDR", ":9090")
	t.Setenv("HOTKEY_DATABASE_URL", "postgres://example")
	t.Setenv("HOTKEY_REDIS_URL", "redis://example")

	cfg := Load()

	if cfg.HTTPAddr != ":9090" {
		t.Fatalf("HTTPAddr = %q, want :9090", cfg.HTTPAddr)
	}
	if cfg.DatabaseURL != "postgres://example" {
		t.Fatalf("DatabaseURL = %q", cfg.DatabaseURL)
	}
	if cfg.RedisURL != "redis://example" {
		t.Fatalf("RedisURL = %q", cfg.RedisURL)
	}
}
