package source

const (
	LayerFact   = "fact"
	LayerSignal = "signal"

	AccessModeOfficialAPI = "official_api"
	AccessModePublicFeed  = "public_feed"
	AccessModeBypass      = "bypass"
)

type Source struct {
	TenantID               string   `json:"tenantId,omitempty"`
	ID                     string   `json:"id"`
	Name                   string   `json:"name"`
	Layer                  string   `json:"layer"`
	Region                 string   `json:"region"`
	Language               string   `json:"language"`
	Categories             []string `json:"categories"`
	AccessMode             string   `json:"accessMode"`
	AuthRequired           bool     `json:"authRequired"`
	Enabled                bool     `json:"enabled"`
	RateLimitPerHour       int      `json:"rateLimitPerHour"`
	RefreshIntervalMinutes int      `json:"refreshIntervalMinutes"`
	ComplianceNote         string   `json:"complianceNote"`
	LastStatus             string   `json:"lastStatus"`
}

type UpdateSourceConfigInput struct {
	Enabled          *bool
	RateLimitPerHour *int
}
