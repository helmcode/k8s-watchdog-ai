package storage

import "time"

type Snapshot struct {
	ID          int64
	ClusterName string
	Timestamp   time.Time
}

type PodSnapshot struct {
	ID             int64
	SnapshotID     int64
	Name           string
	Namespace      string
	Status         string
	RestartCount   int32
	RestartReasons string
	Age            time.Duration
	CPURequest     string
	CPULimit       string
	CPUActual      string
	MemoryRequest  string
	MemoryLimit    string
	MemoryActual   string
}

type NodeSnapshot struct {
	ID                int64
	SnapshotID        int64
	Name              string
	Status            string
	CPUCapacity       string
	CPUAllocatable    string
	MemoryCapacity    string
	MemoryAllocatable string
	Conditions        string
}

type EventSnapshot struct {
	ID         int64
	SnapshotID int64
	Name       string
	Namespace  string
	Type       string
	Reason     string
	Message    string
	Count      int32
	FirstSeen  time.Time
	LastSeen   time.Time
}
