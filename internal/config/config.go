package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	// Required
	AnthropicAPIKey  string
	SlackWebhookURL  string
	SlackChannel     string

	// Optional with defaults
	AnthropicModel    string
	ReportLanguage    string
	ClusterName       string
	NamespacesExclude []string
	SnapshotInterval  time.Duration
	ReportDay         string
	ReportTime        string
	RetentionWeeks    int
	LogLevel          string
	DatabasePath      string
}

func Load() (*Config, error) {
	cfg := &Config{
		// Load required variables
		AnthropicAPIKey: os.Getenv("ANTHROPIC_API_KEY"),
		SlackWebhookURL: os.Getenv("SLACK_WEBHOOK_URL"),
		SlackChannel:    os.Getenv("SLACK_CHANNEL"),

		// Load optional variables with defaults
		AnthropicModel: getEnvOrDefault("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
		ReportLanguage: strings.ToLower(getEnvOrDefault("REPORT_LANGUAGE", "english")),
		ClusterName:    getEnvOrDefault("CLUSTER_NAME", "default"),
		ReportDay:      strings.ToLower(getEnvOrDefault("REPORT_DAY", "monday")),
		ReportTime:     getEnvOrDefault("REPORT_TIME", "09:00"),
		LogLevel:       strings.ToLower(getEnvOrDefault("LOG_LEVEL", "info")),
		DatabasePath:   getEnvOrDefault("DATABASE_PATH", "/data/k8s-observer.db"),
	}

	// Validate required fields
	if cfg.AnthropicAPIKey == "" {
		return nil, fmt.Errorf("ANTHROPIC_API_KEY is required")
	}
	if cfg.SlackWebhookURL == "" {
		return nil, fmt.Errorf("SLACK_WEBHOOK_URL is required")
	}
	if cfg.SlackChannel == "" {
		return nil, fmt.Errorf("SLACK_CHANNEL is required")
	}

	// Parse namespaces to exclude
	excludeStr := getEnvOrDefault("NAMESPACES_EXCLUDE", "kube-system,kube-public,kube-node-lease")
	cfg.NamespacesExclude = parseCommaSeparated(excludeStr)

	// Parse snapshot interval
	intervalStr := getEnvOrDefault("SNAPSHOT_INTERVAL", "3h")
	interval, err := time.ParseDuration(intervalStr)
	if err != nil {
		return nil, fmt.Errorf("invalid SNAPSHOT_INTERVAL: %w", err)
	}
	cfg.SnapshotInterval = interval

	// Parse retention weeks
	retentionStr := getEnvOrDefault("RETENTION_WEEKS", "2")
	retention, err := strconv.Atoi(retentionStr)
	if err != nil {
		return nil, fmt.Errorf("invalid RETENTION_WEEKS: %w", err)
	}
	if retention < 1 {
		return nil, fmt.Errorf("RETENTION_WEEKS must be at least 1")
	}
	cfg.RetentionWeeks = retention

	// Validate report time format
	if _, err := time.Parse("15:04", cfg.ReportTime); err != nil {
		return nil, fmt.Errorf("invalid REPORT_TIME format (expected HH:MM): %w", err)
	}

	// Validate report day
	validDays := map[string]bool{
		"monday": true, "tuesday": true, "wednesday": true, "thursday": true,
		"friday": true, "saturday": true, "sunday": true,
	}
	if !validDays[cfg.ReportDay] {
		return nil, fmt.Errorf("invalid REPORT_DAY: %s", cfg.ReportDay)
	}

	return cfg, nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func parseCommaSeparated(s string) []string {
	if s == "" {
		return []string{}
	}
	parts := strings.Split(s, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		if trimmed := strings.TrimSpace(part); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}
