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

func (c *Collector) collectPods(ctx context.Context, snapshotID int64) error {
	pods, err := c.clientset.CoreV1().Pods("").List(ctx, metav1.ListOptions{})
	if err != nil {
		return fmt.Errorf("failed to list pods: %w", err)
	}

	podMetrics, err := c.metricsClientset.MetricsV1beta1().PodMetricses("").List(ctx, metav1.ListOptions{})
	if err != nil {
		log.Printf("Warning: failed to fetch pod metrics: %v", err)
	}

	metricsMap := make(map[string]map[string]struct {
		cpu    string
		memory string
	})
	if podMetrics != nil {
		for _, pm := range podMetrics.Items {
			metricsMap[pm.Namespace] = make(map[string]struct {
				cpu    string
				memory string
			})
			for _, container := range pm.Containers {
				cpuUsage := container.Usage.Cpu().String()
				memUsage := container.Usage.Memory().String()
				metricsMap[pm.Namespace][pm.Name] = struct {
					cpu    string
					memory string
				}{cpu: cpuUsage, memory: memUsage}
			}
		}
	}

	podCount := 0
	for _, pod := range pods.Items {
		if c.shouldExcludeNamespace(pod.Namespace) {
			continue
		}

		restartCount := int32(0)
		for _, cs := range pod.Status.ContainerStatuses {
			restartCount += cs.RestartCount
		}

		cpuRequest := ""
		cpuLimit := ""
		memRequest := ""
		memLimit := ""

		for _, container := range pod.Spec.Containers {
			if container.Resources.Requests != nil {
				if cpu := container.Resources.Requests[corev1.ResourceCPU]; !cpu.IsZero() {
					cpuRequest = cpu.String()
				}
				if mem := container.Resources.Requests[corev1.ResourceMemory]; !mem.IsZero() {
					memRequest = mem.String()
				}
			}
			if container.Resources.Limits != nil {
				if cpu := container.Resources.Limits[corev1.ResourceCPU]; !cpu.IsZero() {
					cpuLimit = cpu.String()
				}
				if mem := container.Resources.Limits[corev1.ResourceMemory]; !mem.IsZero() {
					memLimit = mem.String()
				}
			}
		}

		cpuActual := ""
		memActual := ""
		if metrics, ok := metricsMap[pod.Namespace][pod.Name]; ok {
			cpuActual = metrics.cpu
			memActual = metrics.memory
		}

		age := time.Since(pod.CreationTimestamp.Time)

		podSnapshot := &storage.PodSnapshot{
			SnapshotID:     snapshotID,
			Name:           pod.Name,
			Namespace:      pod.Namespace,
			Status:         getPodStatus(&pod),
			RestartCount:   restartCount,
			RestartReasons: getRestartReasons(&pod),
			Age:            age,
			CPURequest:     cpuRequest,
			CPULimit:       cpuLimit,
			CPUActual:      cpuActual,
			MemoryRequest:  memRequest,
			MemoryLimit:    memLimit,
			MemoryActual:   memActual,
		}

		if err := c.storage.SavePodSnapshot(podSnapshot); err != nil {
			return fmt.Errorf("failed to save pod snapshot: %w", err)
		}
		podCount++
	}

	log.Printf("Collected %d pods\n", podCount)
	return nil
}
