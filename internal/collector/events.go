package collector

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/helmcloud/k8s-observer/internal/storage"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func (c *Collector) collectEvents(ctx context.Context, snapshotID int64) error {
	events, err := c.clientset.CoreV1().Events("").List(ctx, metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("failed to list events: %w", err)
	}

	eventCount := 0
	recentCutoff := time.Now().Add(-3 * time.Hour)

	for _, event := range events.Items {
		if c.shouldExcludeNamespace(event.Namespace) {
			continue
		}

		if event.Type != corev1.EventTypeWarning && event.Type != corev1.EventTypeNormal {
			continue
		}

		if event.LastTimestamp.Time.Before(recentCutoff) {
			continue
		}

		eventSnapshot := &storage.EventSnapshot{
			SnapshotID: snapshotID,
			Name:       event.InvolvedObject.Name,
			Namespace:  event.Namespace,
			Type:       event.Type,
			Reason:     event.Reason,
			Message:    event.Message,
			Count:      event.Count,
			FirstSeen:  event.FirstTimestamp.Time,
			LastSeen:   event.LastTimestamp.Time,
		}

		if err := c.storage.SaveEventSnapshot(eventSnapshot); err != nil {
			return fmt.Errorf("failed to save event snapshot: %w", err)
		}
		eventCount++
	}

	log.Printf("Collected %d events\n", eventCount)
	return nil
}
