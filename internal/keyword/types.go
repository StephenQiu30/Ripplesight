package keyword

type PlatformKeyword struct {
	TenantID string `json:"tenantId,omitempty"`
	ID       string `json:"id"`
	Term     string `json:"term"`
	Category string `json:"category"`
	Enabled  bool   `json:"enabled"`
}

type CreatePlatformKeywordInput struct {
	TenantID string
	Term     string
	Category string
}

type UserPreferences struct {
	UserID             string   `json:"userId"`
	FollowedKeywords   []string `json:"followedKeywords"`
	BlockedKeywords    []string `json:"blockedKeywords"`
	AdditionalKeywords []string `json:"additionalKeywords"`
}
