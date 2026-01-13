package storage

const schema = `
CREATE TABLE IF NOT EXISTS snapshots (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	cluster_name TEXT NOT NULL,
	timestamp DATETIME NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_snapshots_cluster ON snapshots(cluster_name);

CREATE TABLE IF NOT EXISTS pod_snapshots (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	snapshot_id INTEGER NOT NULL,
	name TEXT NOT NULL,
	namespace TEXT NOT NULL,
	status TEXT NOT NULL,
	restart_count INTEGER NOT NULL DEFAULT 0,
	restart_reasons TEXT,
	age INTEGER NOT NULL,
	cpu_request TEXT,
	cpu_limit TEXT,
	cpu_actual TEXT,
	memory_request TEXT,
	memory_limit TEXT,
	memory_actual TEXT,
	FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pod_snapshots_snapshot ON pod_snapshots(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_pod_snapshots_namespace ON pod_snapshots(namespace);

CREATE TABLE IF NOT EXISTS node_snapshots (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	snapshot_id INTEGER NOT NULL,
	name TEXT NOT NULL,
	status TEXT NOT NULL,
	cpu_capacity TEXT,
	cpu_allocatable TEXT,
	memory_capacity TEXT,
	memory_allocatable TEXT,
	conditions TEXT,
	FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_node_snapshots_snapshot ON node_snapshots(snapshot_id);

CREATE TABLE IF NOT EXISTS event_snapshots (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	snapshot_id INTEGER NOT NULL,
	name TEXT NOT NULL,
	namespace TEXT NOT NULL,
	type TEXT NOT NULL,
	reason TEXT NOT NULL,
	message TEXT,
	count INTEGER NOT NULL DEFAULT 1,
	first_seen DATETIME NOT NULL,
	last_seen DATETIME NOT NULL,
	FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_event_snapshots_snapshot ON event_snapshots(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_event_snapshots_type ON event_snapshots(type);
`
