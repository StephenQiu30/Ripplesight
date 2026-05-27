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

func TestLoadDashScopeDefaults(t *testing.T) {
	t.Setenv("DASHSCOPE_API_KEY", "")
	t.Setenv("DASHSCOPE_BASE_URL", "")
	t.Setenv("DASHSCOPE_CHAT_MODEL", "")
	t.Setenv("DASHSCOPE_EMBEDDING_MODEL", "")
	t.Setenv("EMBEDDING_DIMENSION", "")
	t.Setenv("AI_PROVIDER_ERROR_STRATEGY", "")

	cfg := Load()

	if cfg.DashScopeBaseURL != "https://dashscope.aliyuncs.com/compatible-mode/v1" {
		t.Fatalf("DashScopeBaseURL = %q", cfg.DashScopeBaseURL)
	}
	if cfg.DashScopeChatModel != "qwen-plus" {
		t.Fatalf("DashScopeChatModel = %q, want qwen-plus", cfg.DashScopeChatModel)
	}
	if cfg.DashScopeEmbeddingModel != "text-embedding-v2" {
		t.Fatalf("DashScopeEmbeddingModel = %q, want text-embedding-v2", cfg.DashScopeEmbeddingModel)
	}
	if cfg.EmbeddingDimension != 1536 {
		t.Fatalf("EmbeddingDimension = %d, want 1536", cfg.EmbeddingDimension)
	}
	if cfg.AIProviderErrorStrategy != "fallback" {
		t.Fatalf("AIProviderErrorStrategy = %q, want fallback", cfg.AIProviderErrorStrategy)
	}
}

func TestLoadDashScopeAllowsEnvironmentOverrides(t *testing.T) {
	t.Setenv("DASHSCOPE_API_KEY", "sk-test-key")
	t.Setenv("DASHSCOPE_BASE_URL", "https://custom.example.com/v1")
	t.Setenv("DASHSCOPE_CHAT_MODEL", "qwen-turbo")
	t.Setenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
	t.Setenv("EMBEDDING_DIMENSION", "1024")
	t.Setenv("AI_PROVIDER_ERROR_STRATEGY", "fail")

	cfg := Load()

	if cfg.DashScopeAPIKey != "sk-test-key" {
		t.Fatalf("DashScopeAPIKey = %q", cfg.DashScopeAPIKey)
	}
	if cfg.DashScopeBaseURL != "https://custom.example.com/v1" {
		t.Fatalf("DashScopeBaseURL = %q", cfg.DashScopeBaseURL)
	}
	if cfg.DashScopeChatModel != "qwen-turbo" {
		t.Fatalf("DashScopeChatModel = %q", cfg.DashScopeChatModel)
	}
	if cfg.DashScopeEmbeddingModel != "text-embedding-v3" {
		t.Fatalf("DashScopeEmbeddingModel = %q", cfg.DashScopeEmbeddingModel)
	}
	if cfg.EmbeddingDimension != 1024 {
		t.Fatalf("EmbeddingDimension = %d, want 1024", cfg.EmbeddingDimension)
	}
	if cfg.AIProviderErrorStrategy != "fail" {
		t.Fatalf("AIProviderErrorStrategy = %q", cfg.AIProviderErrorStrategy)
	}
}
