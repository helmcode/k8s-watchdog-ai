package collector

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/helmcloud/k8s-observer/internal/storage"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func (c *Collector) collectNodes(ctx context.Context, snapshotID int64) error {
	nodes, err := c.clientset.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("failed to list nodes: %w", err)
	}

	for _, node := range nodes.Items {
		status := "Ready"
		for _, condition := range node.Status.Conditions {
			if condition.Type == corev1.NodeReady {
				if condition.Status != corev1.ConditionTrue {
					status = "NotReady"
				}
				break
			}
		}

		conditions, err := json.Marshal(node.Status.Conditions)
		if err != nil {
			log.Printf("Warning: failed to marshal node conditions: %v", err)
			conditions = []byte("[]")
		}

		nodeSnapshot := &storage.NodeSnapshot{
			SnapshotID:        snapshotID,
			Name:              node.Name,
			Status:            status,
			CPUCapacity:       getResourceQuantity(node.Status.Capacity, corev1.ResourceCPU),
			CPUAllocatable:    getResourceQuantity(node.Status.Allocatable, corev1.ResourceCPU),
			MemoryCapacity:    getResourceQuantity(node.Status.Capacity, corev1.ResourceMemory),
			MemoryAllocatable: getResourceQuantity(node.Status.Allocatable, corev1.ResourceMemory),
			Conditions:        string(conditions),
		}

		if err := c.storage.SaveNodeSnapshot(nodeSnapshot); err != nil {
			return fmt.Errorf("failed to save node snapshot: %w", err)
		}
	}

	log.Printf("Collected %d nodes\n", len(nodes.Items))
	return nil
}
