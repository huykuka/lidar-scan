/**
 * TDD: Phase 1.2 — Type-check tests for ReloadEvent and SystemStatusBroadcast new field.
 * These tests verify that the new interfaces introduced in status.model.ts are correct
 * per the node-reload-improvement api-spec.md.
 */

import type { ReloadEvent, SystemStatusBroadcast } from './status.model';
import type { NodeStatusUpdate } from './node-status.model';

const makeNodeStatus = (): NodeStatusUpdate => ({
  node_id: 'test-node',
  operational_state: 'RUNNING',
  timestamp: Date.now() / 1000,
});

describe('ReloadEvent interface', () => {
  it('should accept a selective reloading event for a specific node', () => {
    const event: ReloadEvent = {
      node_id: 'a1b2c3d4',
      status: 'reloading',
      error_message: null,
      reload_mode: 'selective',
      timestamp: 1743750000.123,
    };
    expect(event.node_id).toBe('a1b2c3d4');
    expect(event.status).toBe('reloading');
    expect(event.reload_mode).toBe('selective');
  });

  it('should accept a ready event', () => {
    const event: ReloadEvent = {
      node_id: 'a1b2c3d4',
      status: 'ready',
      error_message: null,
      reload_mode: 'selective',
      timestamp: 1743750000.196,
    };
    expect(event.status).toBe('ready');
  });

  it('should accept an error event with error_message', () => {
    const event: ReloadEvent = {
      node_id: 'a1b2c3d4',
      status: 'error',
      error_message: 'Address already in use (port 2115)',
      reload_mode: 'selective',
      timestamp: 1743750000.350,
    };
    expect(event.status).toBe('error');
    expect(event.error_message).toBe('Address already in use (port 2115)');
  });

  it('should accept node_id as null for full DAG reload events', () => {
    const event: ReloadEvent = {
      node_id: null,
      status: 'reloading',
      error_message: null,
      reload_mode: 'full',
      timestamp: 1743750010.000,
    };
    expect(event.node_id).toBeNull();
    expect(event.reload_mode).toBe('full');
  });
});

describe('SystemStatusBroadcast interface', () => {
  it('should accept nodes without reload_event (backward compat)', () => {
    const broadcast: SystemStatusBroadcast = {
      nodes: [makeNodeStatus()],
    };
    expect(broadcast.reload_event).toBeUndefined();
    expect(broadcast.nodes.length).toBe(1);
  });

  it('should accept nodes with optional reload_event', () => {
    const reloadEvent: ReloadEvent = {
      node_id: 'a1b2c3d4',
      status: 'reloading',
      error_message: null,
      reload_mode: 'selective',
      timestamp: 1743750000.123,
    };
    const broadcast: SystemStatusBroadcast = {
      nodes: [makeNodeStatus()],
      reload_event: reloadEvent,
    };
    expect(broadcast.reload_event).toBeDefined();
    expect(broadcast.reload_event?.status).toBe('reloading');
  });
});
