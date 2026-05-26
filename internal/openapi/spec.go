package openapi

type Info struct {
	Title   string `json:"title"`
	Version string `json:"version"`
}

type Operation struct {
	Summary     string                    `json:"summary"`
	OperationID string                    `json:"operationId"`
	Responses   map[string]Response       `json:"responses"`
	Tags        []string                  `json:"tags,omitempty"`
	Extensions  map[string]map[string]any `json:"-"`
}

type Response struct {
	Description string               `json:"description"`
	Content     map[string]MediaType `json:"content,omitempty"`
}

type MediaType struct {
	Schema map[string]any `json:"schema"`
}

type PathItem struct {
	Get Operation `json:"get,omitempty"`
}

type SpecDocument struct {
	OpenAPI string              `json:"openapi"`
	Info    Info                `json:"info"`
	Paths   map[string]PathItem `json:"paths"`
}

func Spec() SpecDocument {
	return SpecDocument{
		OpenAPI: "3.1.0",
		Info: Info{
			Title:   "HotKey Server API",
			Version: "0.1.0",
		},
		Paths: map[string]PathItem{
			"/healthz": {
				Get: Operation{
					Summary:     "Service health check",
					OperationID: "getHealth",
					Tags:        []string{"system"},
					Responses: map[string]Response{
						"200": {
							Description: "Service is healthy",
							Content: map[string]MediaType{
								"application/json": {
									Schema: map[string]any{
										"type": "object",
										"properties": map[string]any{
											"status":  map[string]any{"type": "string"},
											"service": map[string]any{"type": "string"},
										},
										"required": []string{"status", "service"},
									},
								},
							},
						},
					},
				},
			},
			"/openapi.json": {
				Get: Operation{
					Summary:     "Export OpenAPI document",
					OperationID: "getOpenAPI",
					Tags:        []string{"system"},
					Responses: map[string]Response{
						"200": {
							Description: "OpenAPI document",
							Content: map[string]MediaType{
								"application/json": {
									Schema: map[string]any{"type": "object"},
								},
							},
						},
					},
				},
			},
		},
	}
}
