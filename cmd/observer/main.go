package main

import (
	"context"
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/helmcloud/k8s-observer/internal/analyzer"
	"github.com/helmcloud/k8s-observer/internal/collector"
	"github.com/helmcloud/k8s-observer/internal/config"
	"github.com/helmcloud/k8s-observer/internal/pdfgen"
	"github.com/helmcloud/k8s-observer/internal/reporter"
	"github.com/helmcloud/k8s-observer/internal/scheduler"
	"github.com/helmcloud/k8s-observer/internal/storage"
)

func main() {
	testReport := flag.Bool("test-report", false, "Generate and send a test report immediately (for testing purposes)")
	flag.Parse()

	log.Println("Starting K8s Observer...")

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	store, err := storage.New(cfg.DatabasePath)
	if err != nil {
		log.Fatalf("Failed to initialize storage: %v", err)
	}
	defer store.Close()

	col, err := collector.New(store, cfg.ClusterName, cfg.NamespacesExclude)
	if err != nil {
		log.Fatalf("Failed to initialize collector: %v", err)
	}

	ana := analyzer.New(cfg.AnthropicAPIKey, cfg.AnthropicModel, cfg.ReportLanguage, store)

	rep := reporter.New(cfg.SlackWebhookURL, cfg.SlackChannel)

	sched := scheduler.New(
		col,
		ana,
		rep,
		store,
		scheduler.SchedulerConfig{
			ClusterName:      cfg.ClusterName,
			SnapshotInterval: cfg.SnapshotInterval,
			ReportDay:        cfg.ReportDay,
			ReportTime:       cfg.ReportTime,
			RetentionWeeks:   cfg.RetentionWeeks,
		},
	)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if *testReport {
		log.Println("Test report mode enabled - generating report immediately...")

		if err := col.CollectSnapshot(ctx); err != nil {
			log.Fatalf("Failed to collect snapshot for test report: %v", err)
		}

		log.Println("Generating AI analysis...")
		htmlContent, err := ana.GenerateWeeklyReport(ctx, cfg.ClusterName)
		if err != nil {
			log.Fatalf("Failed to generate test report: %v", err)
		}

		log.Println("Generating PDF report from HTML...")
		pdfPath, err := pdfgen.GenerateTempHTMLReportPDF(cfg.ClusterName, htmlContent)
		if err != nil {
			log.Fatalf("Failed to generate PDF: %v", err)
		}
		defer os.Remove(pdfPath)

		log.Printf("PDF generated: %s", pdfPath)
		log.Println("Sending report to Slack...")

		if err := rep.SendReportWithPDF(cfg.ClusterName, pdfPath); err != nil {
			log.Fatalf("Failed to send test report: %v", err)
		}

		log.Println("Test report sent successfully!")
		log.Println("\nExiting test mode.")
		return
	}

	if err := sched.Start(ctx); err != nil {
		log.Fatalf("Failed to start scheduler: %v", err)
	}

	log.Println("K8s Observer is running. Press Ctrl+C to stop.")

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	log.Println("Received shutdown signal")
	sched.Stop()
	log.Println("K8s Observer stopped")
}
