package collector

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"github.com/helmcloud/k8s-observer/internal/storage"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	metricsv1beta1 "k8s.io/metrics/pkg/client/clientset/versioned"
)

type Collector struct {
	clientset        *kubernetes.Clientset
	metricsClientset *metricsv1beta1.Clientset
	storage          *storage.Storage
	clusterName      string
	excludeNS        map[string]bool
}

func New(store *storage.Storage, clusterName string, excludeNamespaces []string) (*Collector, error) {
	config, err := getKubeConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to get kubernetes config: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create kubernetes clientset: %w", err)
	}

	metricsClientset, err := metricsv1beta1.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create metrics clientset: %w", err)
	}

	excludeMap := make(map[string]bool)
	for _, ns := range excludeNamespaces {
		excludeMap[ns] = true
	}

	return &Collector{
		clientset:        clientset,
		metricsClientset: metricsClientset,
		storage:          store,
		clusterName:      clusterName,
		excludeNS:        excludeMap,
	}, nil
}

func getKubeConfig() (*rest.Config, error) {
	config, err := rest.InClusterConfig()
	if err == nil {
		log.Println("Using in-cluster kubernetes config")
		return config, nil
	}

	log.Println("Not running in cluster, trying local kubeconfig...")

	kubeconfigPath := os.Getenv("KUBECONFIG")
	if kubeconfigPath == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("failed to get home directory: %w", err)
		}
		kubeconfigPath = filepath.Join(homeDir, ".kube", "config")
	}

	config, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	if err != nil {
		return nil, fmt.Errorf("failed to build config from kubeconfig: %w", err)
	}

	log.Printf("Using kubeconfig from: %s\n", kubeconfigPath)
	return config, nil
}

func (c *Collector) CollectSnapshot(ctx context.Context) error {
	log.Println("Starting snapshot collection...")
	timestamp := time.Now()

	snapshotID, err := c.storage.CreateSnapshot(c.clusterName, timestamp)
	if err != nil {
		return fmt.Errorf("failed to create snapshot: %w", err)
	}

	if err := c.collectPods(ctx, snapshotID); err != nil {
		return fmt.Errorf("failed to collect pods: %w", err)
	}

	if err := c.collectNodes(ctx, snapshotID); err != nil {
		return fmt.Errorf("failed to collect nodes: %w", err)
	}

	if err := c.collectEvents(ctx, snapshotID); err != nil {
		return fmt.Errorf("failed to collect events: %w", err)
	}

	log.Printf("Snapshot collection completed (ID: %d)\n", snapshotID)
	return nil
}

func (c *Collector) shouldExcludeNamespace(ns string) bool {
	return c.excludeNS[ns]
}

func getPodStatus(pod *corev1.Pod) string {
	if pod.Status.Phase == corev1.PodRunning {
		for _, cs := range pod.Status.ContainerStatuses {
			if cs.State.Waiting != nil {
				return fmt.Sprintf("Waiting: %s", cs.State.Waiting.Reason)
			}
			if cs.State.Terminated != nil {
				return fmt.Sprintf("Terminated: %s", cs.State.Terminated.Reason)
			}
		}
	}
	return string(pod.Status.Phase)
}

func getRestartReasons(pod *corev1.Pod) string {
	reasons := make(map[string]int)
	for _, cs := range pod.Status.ContainerStatuses {
		if cs.LastTerminationState.Terminated != nil {
			reason := cs.LastTerminationState.Terminated.Reason
			if reason == "" {
				reason = "Unknown"
			}
			reasons[reason]++
		}
	}

	if len(reasons) == 0 {
		return ""
	}

	result := ""
	for reason, count := range reasons {
		if result != "" {
			result += ", "
		}
		result += fmt.Sprintf("%s(%d)", reason, count)
	}
	return result
}

func getResourceQuantity(resources corev1.ResourceList, resourceName corev1.ResourceName) string {
	if qty, ok := resources[resourceName]; ok {
		return qty.String()
	}
	return ""
}
