package scheduler

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/helmcloud/k8s-observer/internal/analyzer"
	"github.com/helmcloud/k8s-observer/internal/collector"
	"github.com/helmcloud/k8s-observer/internal/pdfgen"
	"github.com/helmcloud/k8s-observer/internal/reporter"
	"github.com/helmcloud/k8s-observer/internal/storage"
	"github.com/robfig/cron/v3"
)

type Scheduler struct {
	cron      *cron.Cron
	collector *collector.Collector
	analyzer  *analyzer.Analyzer
	reporter  *reporter.Reporter
	storage   *storage.Storage
	config    SchedulerConfig
}

type SchedulerConfig struct {
	ClusterName      string
	SnapshotInterval time.Duration
	ReportDay        string
	ReportTime       string
	RetentionWeeks   int
}

func New(
	col *collector.Collector,
	ana *analyzer.Analyzer,
	rep *reporter.Reporter,
	store *storage.Storage,
	cfg SchedulerConfig,
) *Scheduler {
	return &Scheduler{
		cron:      cron.New(),
		collector: col,
		analyzer:  ana,
		reporter:  rep,
		storage:   store,
		config:    cfg,
	}
}

func (s *Scheduler) Start(ctx context.Context) error {
	snapshotCron := fmt.Sprintf("@every %s", s.config.SnapshotInterval)
	_, err := s.cron.AddFunc(snapshotCron, func() {
		if err := s.runSnapshot(ctx); err != nil {
			log.Printf("Error running snapshot: %v", err)
		}
	})
	if err != nil {
		return fmt.Errorf("failed to schedule snapshot job: %w", err)
	}

	reportCron, err := s.buildReportCronExpression()
	if err != nil {
		return fmt.Errorf("failed to build report cron expression: %w", err)
	}

	_, err = s.cron.AddFunc(reportCron, func() {
		if err := s.runWeeklyReport(ctx); err != nil {
			log.Printf("Error running weekly report: %v", err)
		}
	})
	if err != nil {
		return fmt.Errorf("failed to schedule report job: %w", err)
	}

	cleanupCron := "0 2 * * *"
	_, err = s.cron.AddFunc(cleanupCron, func() {
		if err := s.runCleanup(); err != nil {
			log.Printf("Error running cleanup: %v", err)
		}
	})
	if err != nil {
		return fmt.Errorf("failed to schedule cleanup job: %w", err)
	}

	log.Println("Starting scheduler...")
	log.Printf("Snapshot collection: %s", snapshotCron)
	log.Printf("Weekly report: %s", reportCron)
	log.Printf("Cleanup: %s", cleanupCron)

	s.cron.Start()

	if err := s.runSnapshot(ctx); err != nil {
		log.Printf("Error running initial snapshot: %v", err)
	}

	return nil
}

func (s *Scheduler) Stop() {
	log.Println("Stopping scheduler...")
	s.cron.Stop()
}

func (s *Scheduler) runSnapshot(ctx context.Context) error {
	log.Println("Running scheduled snapshot collection...")
	if err := s.collector.CollectSnapshot(ctx); err != nil {
		return fmt.Errorf("snapshot collection failed: %w", err)
	}
	return nil
}

func (s *Scheduler) runWeeklyReport(ctx context.Context) error {
	log.Println("Running scheduled weekly report...")

	htmlContent, err := s.analyzer.GenerateWeeklyReport(ctx, s.config.ClusterName)
	if err != nil {
		return fmt.Errorf("failed to generate report: %w", err)
	}

	log.Println("Generating PDF report from HTML...")
	pdfPath, err := pdfgen.GenerateTempHTMLReportPDF(s.config.ClusterName, htmlContent)
	if err != nil {
		return fmt.Errorf("failed to generate PDF: %w", err)
	}
	defer os.Remove(pdfPath)

	log.Printf("PDF generated: %s", pdfPath)

	if err := s.reporter.SendReportWithPDF(s.config.ClusterName, pdfPath); err != nil {
		return fmt.Errorf("failed to send report: %w", err)
	}

	log.Println("Weekly report sent successfully")
	return nil
}

func (s *Scheduler) runCleanup() error {
	log.Println("Running scheduled cleanup...")
	if err := s.storage.CleanupOldSnapshots(s.config.RetentionWeeks); err != nil {
		return fmt.Errorf("cleanup failed: %w", err)
	}
	log.Println("Cleanup completed")
	return nil
}

func (s *Scheduler) buildReportCronExpression() (string, error) {
	timeParts := strings.Split(s.config.ReportTime, ":")
	if len(timeParts) != 2 {
		return "", fmt.Errorf("invalid report time format: %s", s.config.ReportTime)
	}

	hour := timeParts[0]
	minute := timeParts[1]

	dayMap := map[string]string{
		"sunday":    "0",
		"monday":    "1",
		"tuesday":   "2",
		"wednesday": "3",
		"thursday":  "4",
		"friday":    "5",
		"saturday":  "6",
	}

	day, ok := dayMap[strings.ToLower(s.config.ReportDay)]
	if !ok {
		return "", fmt.Errorf("invalid report day: %s", s.config.ReportDay)
	}

	return fmt.Sprintf("%s %s * * %s", minute, hour, day), nil
}
