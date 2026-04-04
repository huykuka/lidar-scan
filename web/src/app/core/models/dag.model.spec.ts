/**
 * TDD: Phase 1.1 — Type-check tests for DagConfigSaveResponse new fields.
 * These tests verify that the TypeScript interfaces accept the new reload_mode
 * and reloaded_node_ids fields introduced by the node-reload-improvement feature.
 */

import type { DagConfigSaveResponse } from './dag.model';

describe('DagConfigSaveResponse interface', () => {
  it('should accept reload_mode "selective" with reloaded_node_ids', () => {
    const response: DagConfigSaveResponse = {
      config_version: 8,
      node_id_map: {},
      reload_mode: 'selective',
      reloaded_node_ids: ['a1b2c3d4'],
    };
    expect(response.reload_mode).toBe('selective');
    expect(response.reloaded_node_ids).toEqual(['a1b2c3d4']);
  });

  it('should accept reload_mode "full" with empty reloaded_node_ids', () => {
    const response: DagConfigSaveResponse = {
      config_version: 9,
      node_id_map: { '__new__1': 'e5f6a7b8' },
      reload_mode: 'full',
      reloaded_node_ids: [],
    };
    expect(response.reload_mode).toBe('full');
    expect(response.reloaded_node_ids).toEqual([]);
  });

  it('should accept reload_mode "none" with empty reloaded_node_ids', () => {
    const response: DagConfigSaveResponse = {
      config_version: 10,
      node_id_map: {},
      reload_mode: 'none',
      reloaded_node_ids: [],
    };
    expect(response.reload_mode).toBe('none');
    expect(response.reloaded_node_ids).toEqual([]);
  });

  it('should carry config_version and node_id_map as before', () => {
    const response: DagConfigSaveResponse = {
      config_version: 42,
      node_id_map: { temp: 'real' },
      reload_mode: 'selective',
      reloaded_node_ids: ['real'],
    };
    expect(response.config_version).toBe(42);
    expect(response.node_id_map).toEqual({ temp: 'real' });
  });
});
