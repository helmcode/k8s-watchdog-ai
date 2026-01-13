package analyzer

import (
	"context"
	"fmt"
	"time"

	anthropic "github.com/liushuangls/go-anthropic/v2"
	"github.com/helmcloud/k8s-observer/internal/storage"
)

type Analyzer struct {
	client   *anthropic.Client
	storage  *storage.Storage
	model    string
	language string
}

type ClusterData struct {
	ClusterName  string
	CurrentWeek  *WeekData
	PreviousWeek *WeekData
}

type WeekData struct {
	Snapshots []storage.Snapshot
	Pods      []PodData
	Nodes     []NodeData
	Events    []EventData
}

type PodData struct {
	Name           string
	Namespace      string
	Status         string
	RestartCount   string
	RestartReasons string
	CPURequest     string
	CPULimit       string
	CPUActual      string
	MemoryRequest  string
	MemoryLimit    string
	MemoryActual   string
}

type NodeData struct {
	Name              string
	Status            string
	CPUCapacity       string
	CPUAllocatable    string
	MemoryCapacity    string
	MemoryAllocatable string
}

type EventData struct {
	Name      string
	Namespace string
	Type      string
	Reason    string
	Message   string
	Count     string
}

func New(apiKey string, model string, language string, store *storage.Storage) *Analyzer {
	client := anthropic.NewClient(apiKey)
	return &Analyzer{
		client:   client,
		storage:  store,
		model:    model,
		language: language,
	}
}

func (a *Analyzer) GenerateWeeklyReport(ctx context.Context, clusterName string) (string, error) {
	data, err := a.prepareClusterData(clusterName)
	if err != nil {
		return "", fmt.Errorf("failed to prepare cluster data: %w", err)
	}

	prompt := buildAnalysisPrompt(data)

	req := anthropic.MessagesRequest{
		Model:     anthropic.Model(a.model),
		MaxTokens: 8192,
		System:    getSystemPrompt(a.language),
		Messages: []anthropic.Message{
			anthropic.NewUserTextMessage(prompt),
		},
	}

	resp, err := a.client.CreateMessages(ctx, req)
	if err != nil {
		return "", fmt.Errorf("failed to call Claude API: %w", err)
	}

	if len(resp.Content) == 0 {
		return "", fmt.Errorf("received empty response from Claude API")
	}

	return resp.Content[0].GetText(), nil
}

func (a *Analyzer) prepareClusterData(clusterName string) (*ClusterData, error) {
	now := time.Now()

	currentWeekStart := now.AddDate(0, 0, -7)
	currentWeekEnd := now

	currentWeek, err := a.getWeekData(currentWeekStart, currentWeekEnd)
	if err != nil {
		return nil, fmt.Errorf("failed to get current week data: %w", err)
	}

	return &ClusterData{
		ClusterName:  clusterName,
		CurrentWeek:  currentWeek,
		PreviousWeek: nil, // No longer comparing with previous week
	}, nil
}

func (a *Analyzer) getWeekData(start, end time.Time) (*WeekData, error) {
	snapshots, err := a.storage.GetSnapshotsInRange(start, end)
	if err != nil {
		return nil, fmt.Errorf("failed to get snapshots: %w", err)
	}

	if len(snapshots) == 0 {
		return &WeekData{}, nil
	}

	latestSnapshot := snapshots[0]

	pods, err := a.storage.GetPodSnapshots(latestSnapshot.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get pod snapshots: %w", err)
	}

	nodes, err := a.storage.GetNodeSnapshots(latestSnapshot.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get node snapshots: %w", err)
	}

	events, err := a.storage.GetEventSnapshots(latestSnapshot.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get event snapshots: %w", err)
	}

	weekData := &WeekData{
		Snapshots: snapshots,
		Pods:      make([]PodData, len(pods)),
		Nodes:     make([]NodeData, len(nodes)),
		Events:    make([]EventData, len(events)),
	}

	for i, pod := range pods {
		weekData.Pods[i] = PodData{
			Name:           pod.Name,
			Namespace:      pod.Namespace,
			Status:         pod.Status,
			RestartCount:   fmt.Sprintf("%d", pod.RestartCount),
			RestartReasons: pod.RestartReasons,
			CPURequest:     pod.CPURequest,
			CPULimit:       pod.CPULimit,
			CPUActual:      pod.CPUActual,
			MemoryRequest:  pod.MemoryRequest,
			MemoryLimit:    pod.MemoryLimit,
			MemoryActual:   pod.MemoryActual,
		}
	}

	for i, node := range nodes {
		weekData.Nodes[i] = NodeData{
			Name:              node.Name,
			Status:            node.Status,
			CPUCapacity:       node.CPUCapacity,
			CPUAllocatable:    node.CPUAllocatable,
			MemoryCapacity:    node.MemoryCapacity,
			MemoryAllocatable: node.MemoryAllocatable,
		}
	}

	for i, event := range events {
		weekData.Events[i] = EventData{
			Name:      event.Name,
			Namespace: event.Namespace,
			Type:      event.Type,
			Reason:    event.Reason,
			Message:   event.Message,
			Count:     fmt.Sprintf("%d", event.Count),
		}
	}

	return weekData, nil
}
