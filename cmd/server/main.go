package main

import (
	"log"
	"net/http"
	"os"

	"github.com/StephenQiu30/hotkey-server/internal/config"
	"github.com/StephenQiu30/hotkey-server/internal/httpapi"
	"github.com/gin-gonic/gin"
)

func main() {
	if os.Getenv("GIN_MODE") == "" {
		gin.SetMode(gin.ReleaseMode)
	}

	cfg := config.Load()
	server := &http.Server{
		Addr:    cfg.HTTPAddr,
		Handler: httpapi.NewRouter(),
	}

	log.Printf("hotkey-server listening on %s", cfg.HTTPAddr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server stopped: %v", err)
	}
}
