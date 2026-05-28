package hotspot

const (
	SortByHeat      = "heat"
	SortByTrust     = "trust"
	SortByRelevance = "relevance"
)

type RelatedContent struct {
	SourceItemID string `json:"sourceItemId"`
	Title        string `json:"title"`
	URL          string `json:"url"`
}

type EvidenceDetail struct {
	FactEvidenceIDs   []string `json:"factEvidenceIds"`
	SignalEvidenceIDs []string `json:"signalEvidenceIds"`
	RiskLabels        []string `json:"riskLabels"`
}

type HotspotSummary struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Keywords        []string `json:"keywords"`
	Region          string   `json:"region"`
	Language        string   `json:"language"`
	HeatScore       int      `json:"heatScore"`
	TrustScore      int      `json:"trustScore"`
	SimilarityScore float64  `json:"similarityScore"`
	RelevanceScore  float64  `json:"relevanceScore"`
}

type HotspotDetail struct {
	HotspotSummary
	RelatedContent []RelatedContent `json:"relatedContent"`
	Evidence       EvidenceDetail   `json:"evidence"`
}

type HotspotInput struct {
	ID              string
	Title           string
	Keywords        []string
	Region          string
	Language        string
	HeatScore       int
	TrustScore      int
	SimilarityScore float64
	RelatedContent  []RelatedContent
	Evidence        EvidenceDetail
}

type ListOptions struct {
	Keyword  string
	Region   string
	Language string
	MinTrust int
	SortBy   string
}
