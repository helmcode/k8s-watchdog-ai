package storage

import (
	"database/sql"
	"fmt"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Storage struct {
	db *sql.DB
}

func New(dbPath string) (*Storage, error) {
	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	s := &Storage{db: db}

	if err := s.migrate(); err != nil {
		return nil, fmt.Errorf("failed to migrate database: %w", err)
	}

	return s, nil
}

func (s *Storage) migrate() error {
	_, err := s.db.Exec(schema)
	if err != nil {
		return fmt.Errorf("failed to execute schema: %w", err)
	}
	return nil
}

func (s *Storage) Close() error {
	return s.db.Close()
}

func (s *Storage) CreateSnapshot(clusterName string, timestamp time.Time) (int64, error) {
	result, err := s.db.Exec(
		"INSERT INTO snapshots (cluster_name, timestamp) VALUES (?, ?)",
		clusterName, timestamp,
	)
	if err != nil {
		return 0, fmt.Errorf("failed to create snapshot: %w", err)
	}
	return result.LastInsertId()
}

func (s *Storage) SavePodSnapshot(pod *PodSnapshot) error {
	_, err := s.db.Exec(`
		INSERT INTO pod_snapshots (
			snapshot_id, name, namespace, status, restart_count, restart_reasons,
			age, cpu_request, cpu_limit, cpu_actual, memory_request, memory_limit, memory_actual
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		pod.SnapshotID, pod.Name, pod.Namespace, pod.Status, pod.RestartCount,
		pod.RestartReasons, pod.Age, pod.CPURequest, pod.CPULimit, pod.CPUActual,
		pod.MemoryRequest, pod.MemoryLimit, pod.MemoryActual,
	)
	if err != nil {
		return fmt.Errorf("failed to save pod snapshot: %w", err)
	}
	return nil
}

func (s *Storage) SaveNodeSnapshot(node *NodeSnapshot) error {
	_, err := s.db.Exec(`
		INSERT INTO node_snapshots (
			snapshot_id, name, status, cpu_capacity, cpu_allocatable,
			memory_capacity, memory_allocatable, conditions
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		node.SnapshotID, node.Name, node.Status, node.CPUCapacity, node.CPUAllocatable,
		node.MemoryCapacity, node.MemoryAllocatable, node.Conditions,
	)
	if err != nil {
		return fmt.Errorf("failed to save node snapshot: %w", err)
	}
	return nil
}

func (s *Storage) SaveEventSnapshot(event *EventSnapshot) error {
	_, err := s.db.Exec(`
		INSERT INTO event_snapshots (
			snapshot_id, name, namespace, type, reason, message, count, first_seen, last_seen
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		event.SnapshotID, event.Name, event.Namespace, event.Type, event.Reason,
		event.Message, event.Count, event.FirstSeen, event.LastSeen,
	)
	if err != nil {
		return fmt.Errorf("failed to save event snapshot: %w", err)
	}
	return nil
}

func (s *Storage) GetSnapshotsInRange(start, end time.Time) ([]Snapshot, error) {
	rows, err := s.db.Query(`
		SELECT id, cluster_name, timestamp
		FROM snapshots
		WHERE timestamp BETWEEN ? AND ?
		ORDER BY timestamp DESC`,
		start, end,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query snapshots: %w", err)
	}
	defer rows.Close()

	var snapshots []Snapshot
	for rows.Next() {
		var snap Snapshot
		if err := rows.Scan(&snap.ID, &snap.ClusterName, &snap.Timestamp); err != nil {
			return nil, fmt.Errorf("failed to scan snapshot: %w", err)
		}
		snapshots = append(snapshots, snap)
	}

	return snapshots, rows.Err()
}

func (s *Storage) GetPodSnapshots(snapshotID int64) ([]PodSnapshot, error) {
	rows, err := s.db.Query(`
		SELECT id, snapshot_id, name, namespace, status, restart_count, restart_reasons,
			age, cpu_request, cpu_limit, cpu_actual, memory_request, memory_limit, memory_actual
		FROM pod_snapshots
		WHERE snapshot_id = ?`,
		snapshotID,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query pod snapshots: %w", err)
	}
	defer rows.Close()

	var pods []PodSnapshot
	for rows.Next() {
		var pod PodSnapshot
		if err := rows.Scan(
			&pod.ID, &pod.SnapshotID, &pod.Name, &pod.Namespace, &pod.Status,
			&pod.RestartCount, &pod.RestartReasons, &pod.Age, &pod.CPURequest,
			&pod.CPULimit, &pod.CPUActual, &pod.MemoryRequest, &pod.MemoryLimit, &pod.MemoryActual,
		); err != nil {
			return nil, fmt.Errorf("failed to scan pod snapshot: %w", err)
		}
		pods = append(pods, pod)
	}

	return pods, rows.Err()
}

func (s *Storage) GetNodeSnapshots(snapshotID int64) ([]NodeSnapshot, error) {
	rows, err := s.db.Query(`
		SELECT id, snapshot_id, name, status, cpu_capacity, cpu_allocatable,
			memory_capacity, memory_allocatable, conditions
		FROM node_snapshots
		WHERE snapshot_id = ?`,
		snapshotID,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query node snapshots: %w", err)
	}
	defer rows.Close()

	var nodes []NodeSnapshot
	for rows.Next() {
		var node NodeSnapshot
		if err := rows.Scan(
			&node.ID, &node.SnapshotID, &node.Name, &node.Status,
			&node.CPUCapacity, &node.CPUAllocatable, &node.MemoryCapacity,
			&node.MemoryAllocatable, &node.Conditions,
		); err != nil {
			return nil, fmt.Errorf("failed to scan node snapshot: %w", err)
		}
		nodes = append(nodes, node)
	}

	return nodes, rows.Err()
}

func (s *Storage) GetEventSnapshots(snapshotID int64) ([]EventSnapshot, error) {
	rows, err := s.db.Query(`
		SELECT id, snapshot_id, name, namespace, type, reason, message, count, first_seen, last_seen
		FROM event_snapshots
		WHERE snapshot_id = ?`,
		snapshotID,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query event snapshots: %w", err)
	}
	defer rows.Close()

	var events []EventSnapshot
	for rows.Next() {
		var event EventSnapshot
		if err := rows.Scan(
			&event.ID, &event.SnapshotID, &event.Name, &event.Namespace,
			&event.Type, &event.Reason, &event.Message, &event.Count,
			&event.FirstSeen, &event.LastSeen,
		); err != nil {
			return nil, fmt.Errorf("failed to scan event snapshot: %w", err)
		}
		events = append(events, event)
	}

	return events, rows.Err()
}

func (s *Storage) CleanupOldSnapshots(retentionWeeks int) error {
	cutoff := time.Now().AddDate(0, 0, -retentionWeeks*7)
	_, err := s.db.Exec("DELETE FROM snapshots WHERE timestamp < ?", cutoff)
	if err != nil {
		return fmt.Errorf("failed to cleanup old snapshots: %w", err)
	}
	return nil
}
