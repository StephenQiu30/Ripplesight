package httpapi

import (
	"net/http"

	"github.com/StephenQiu30/hotkey-server/internal/openapi"
	"github.com/gin-gonic/gin"
)

func NewRouter() *gin.Engine {
	router := gin.New()
	router.Use(gin.Recovery())
	router.GET("/healthz", handleHealth)
	router.GET("/openapi.json", handleOpenAPI)
	return router
}

func handleHealth(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"service": "hotkey-server",
	})
}

func handleOpenAPI(c *gin.Context) {
	c.JSON(http.StatusOK, openapi.Spec())
}
