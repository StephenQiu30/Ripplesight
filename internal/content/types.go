package content

import "time"

const (
	ResultCreated   = "created"
	ResultDuplicate = "duplicate"
)

type SourceItem struct {
	ID           string            `json:"id"`
	SourceID     string            `json:"sourceId"`
	OriginalURL  string            `json:"originalUrl"`
	CanonicalURL string            `json:"canonicalUrl"`
	Title        string            `json:"title"`
	Summary      string            `json:"summary"`
	PublishedAt  time.Time         `json:"publishedAt"`
	FetchedAt    time.Time         `json:"fetchedAt"`
	ContentHash  string            `json:"contentHash"`
	RawMetadata  map[string]string `json:"rawMetadata"`
}

type IngestSourceItemInput struct {
	SourceID    string
	OriginalURL string
	Title       string
	Summary     string
	PublishedAt time.Time
	FetchedAt   time.Time
	RawMetadata map[string]string
}
