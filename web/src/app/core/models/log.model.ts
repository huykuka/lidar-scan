/**
 * Log Entry Model
 * Represents a single parsed log line from the backend
 */
export interface LogEntry {
  timestamp: string;      // ISO format: "2024-02-23 12:34:56,123"
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  module: string;         // e.g., "app", "lidar.sensor", "websocket.manager"
  message: string;        // Log message text
}

/**
 * Log Filter Options
 */
export interface LogFilterOptions {
  level?: string;         // Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  search?: string;        // Free text search in message
  offset?: number;        // Pagination offset (default 0, newest first)
  limit?: number;         // Number of entries to return (default 100, max 500)
}

/**
 * Log API Response for REST endpoint
 */
export interface LogsResponse {
  entries: LogEntry[];
  total?: number;
  offset?: number;
  limit?: number;
}
