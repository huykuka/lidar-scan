/**
 * TDD: Environment Filtering Node — Palette Registration & Status Display
 *
 * Covers:
 *  - Phase 1: auto-discovery of `environment_filtering` from node definitions
 *  - Phase 1: `layers_clear` icon resolves on the palette card
 *  - Phase 2: `planes_filtered` badge with orange/blue/red color states
 *  - Phase 3: `voxel_downsample_size` property present in mock schema (14 props)
 *
 * api-spec.md reference: § 1, § 3, § 6
 */

import {signal} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {ComponentFixture} from '@angular/core/testing';

import {FlowCanvasPaletteComponent} from '@features/settings/components/flow-canvas/palette/flow-canvas-palette.component';
import {FlowCanvasNodeComponent, CanvasNode} from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {NodeDefinition, PropertySchema} from '@core/models/node.model';
import {NodePlugin} from '@core/models';
import {NodeStatusUpdate} from '@core/models/node-status.model';

// ---------------------------------------------------------------------------
// Mock NodeDefinition for environment_filtering — api-spec.md § 1 & § 3
// ---------------------------------------------------------------------------
export const MOCK_ENV_FILTER_DEFINITION: NodeDefinition = {
  type: 'environment_filtering',
  display_name: 'Environment Filtering',
  category: 'application',
  description: 'Removes floor and ceiling planes from the point cloud.',
  icon: 'layers_clear',
  websocket_enabled: true,
  inputs: [{id: 'in', label: 'Input Point Cloud', data_type: 'pointcloud', multiple: false}],
  outputs: [{id: 'out', label: 'Filtered Point Cloud', data_type: 'pointcloud', multiple: false}],
  properties: [
    // Group A — Performance
    {name: 'throttle_ms', label: 'Throttle (ms)', type: 'number', default: 0, min: 0, step: 10},
    {name: 'voxel_downsample_size', label: 'Voxel Downsample Size (m)', type: 'number', default: 0.01, min: 0.0, max: 1.0, step: 0.005, help_text: 'Reduce point cloud density before plane detection...'},
    // Group B — Plane Detection
    {name: 'normal_variance_threshold_deg', label: 'Normal Variance (deg)', type: 'number', default: 60.0, min: 1.0, max: 90.0, step: 1.0},
    {name: 'coplanarity_deg', label: 'Coplanarity (deg)', type: 'number', default: 75.0, min: 1.0, max: 90.0, step: 1.0},
    {name: 'outlier_ratio', label: 'Outlier Ratio', type: 'number', default: 0.75, min: 0.0, max: 1.0, step: 0.05},
    {name: 'min_plane_edge_length', label: 'Min Edge Length (m)', type: 'number', default: 0.0, min: 0.0, step: 0.01},
    {name: 'min_num_points', label: 'Min Points', type: 'number', default: 0, min: 0, step: 1},
    {name: 'knn', label: 'KNN', type: 'number', default: 30, min: 5, max: 100, step: 1},
    // Group C — Validation
    {name: 'vertical_tolerance_deg', label: 'Vertical Tolerance (deg)', type: 'number', default: 15.0, min: 1.0, max: 45.0, step: 0.5},
    {name: 'floor_height_min', label: 'Floor Height Min (m)', type: 'number', default: -0.5, step: 0.1},
    {name: 'floor_height_max', label: 'Floor Height Max (m)', type: 'number', default: 0.5, step: 0.1},
    {name: 'ceiling_height_min', label: 'Ceiling Height Min (m)', type: 'number', default: 2.0, step: 0.1},
    {name: 'ceiling_height_max', label: 'Ceiling Height Max (m)', type: 'number', default: 4.0, step: 0.1},
    {name: 'min_plane_area', label: 'Min Plane Area (m²)', type: 'number', default: 1.0, min: 0.1, step: 0.1},
  ] as PropertySchema[],
};

// ---------------------------------------------------------------------------
// Helper — build a NodePlugin from the definition (mirrors definitionToPlugin)
// ---------------------------------------------------------------------------
function makeEnvFilterPlugin(): NodePlugin {
  return {
    type: 'environment_filtering',
    category: 'application',
    displayName: 'Environment Filtering',
    description: 'Removes floor and ceiling planes from the point cloud.',
    icon: 'layers_clear',
    style: {color: '#0891b2'}, // application category teal
    ports: {
      inputs: [{id: 'in', label: 'Input Point Cloud', dataType: 'pointcloud', multiple: false}],
      outputs: [{id: 'out', label: 'Filtered Point Cloud', dataType: 'pointcloud', multiple: false}],
    },
    createInstance: () => ({
      type: 'environment_filtering',
      category: 'application',
      name: 'Environment Filtering',
      enabled: true,
      config: {
        throttle_ms: 0,
        voxel_downsample_size: 0.01,
        normal_variance_threshold_deg: 60.0,
        coplanarity_deg: 75.0,
        outlier_ratio: 0.75,
        min_plane_edge_length: 0.0,
        min_num_points: 0,
        knn: 30,
        vertical_tolerance_deg: 15.0,
        floor_height_min: -0.5,
        floor_height_max: 0.5,
        ceiling_height_min: 2.0,
        ceiling_height_max: 4.0,
        min_plane_area: 1.0,
      },
    }),
    renderBody: () => ({fields: []}),
  };
}

// ---------------------------------------------------------------------------
// Phase 1 — Palette Registration
// ---------------------------------------------------------------------------
describe('Environment Filtering — Phase 1: Palette Registration', () => {

  describe('Mock NodeDefinition schema (api-spec.md § 3)', () => {
    it('should have exactly 14 properties', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.properties.length).toBe(14);
    });

    it('should include voxel_downsample_size with correct constraints', () => {
      const prop = MOCK_ENV_FILTER_DEFINITION.properties.find(p => p.name === 'voxel_downsample_size');
      expect(prop).toBeDefined();
      expect(prop!.type).toBe('number');
      expect(prop!.default).toBe(0.01);
      expect(prop!.min).toBe(0.0);
      expect(prop!.max).toBe(1.0);
      expect(prop!.step).toBe(0.005);
    });

    it('should use icon "layers_clear" (Synergy SICK 2025 iconset)', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.icon).toBe('layers_clear');
    });

    it('should be in category "application"', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.category).toBe('application');
    });

    it('should have websocket_enabled=true (LIDR protocol streams output)', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.websocket_enabled).toBe(true);
    });

    it('should have one input port "in" of type pointcloud', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.inputs.length).toBe(1);
      expect(MOCK_ENV_FILTER_DEFINITION.inputs[0].id).toBe('in');
      expect(MOCK_ENV_FILTER_DEFINITION.inputs[0].data_type).toBe('pointcloud');
    });

    it('should have one output port "out" of type pointcloud', () => {
      expect(MOCK_ENV_FILTER_DEFINITION.outputs.length).toBe(1);
      expect(MOCK_ENV_FILTER_DEFINITION.outputs[0].id).toBe('out');
      expect(MOCK_ENV_FILTER_DEFINITION.outputs[0].data_type).toBe('pointcloud');
    });
  });

  describe('FlowCanvasPaletteComponent — environment_filtering visibility', () => {
    let fixture: ComponentFixture<FlowCanvasPaletteComponent>;

    beforeEach(async () => {
      if (!(Element.prototype as any).getAnimations) {
        (Element.prototype as any).getAnimations = () => [];
      }

      await TestBed.configureTestingModule({
        imports: [FlowCanvasPaletteComponent],
      }).compileComponents();

      fixture = TestBed.createComponent(FlowCanvasPaletteComponent);
    });

    it('should render environment_filtering node in the palette when definition is provided', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const compiled: HTMLElement = fixture.nativeElement;
      expect(compiled.textContent).toContain('Environment Filtering');
    });

    it('should render the "application" category group header', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const compiled: HTMLElement = fixture.nativeElement;
      // The category header text should include "application"
      expect(compiled.textContent?.toLowerCase()).toContain('application');
    });

    it('should include environment_filtering in filteredPlugins when query matches display name', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const comp = fixture.componentInstance;
      comp.searchQuery.set('environment');
      fixture.detectChanges();

      expect(comp.filteredPlugins().length).toBe(1);
      expect(comp.filteredPlugins()[0].type).toBe('environment_filtering');
    });

    it('should include environment_filtering in filteredPlugins when query matches category', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const comp = fixture.componentInstance;
      comp.searchQuery.set('application');
      fixture.detectChanges();

      expect(comp.filteredPlugins().length).toBe(1);
    });

    it('should exclude environment_filtering when search query does not match', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const comp = fixture.componentInstance;
      comp.searchQuery.set('sensor');
      fixture.detectChanges();

      expect(comp.filteredPlugins().length).toBe(0);
    });

    it('should group environment_filtering under category "application"', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const comp = fixture.componentInstance;
      const groups = comp.groupedPlugins();
      const appGroup = groups.find(g => g.category === 'application');

      expect(appGroup).toBeDefined();
      expect(appGroup!.plugins.length).toBe(1);
      expect(appGroup!.plugins[0].type).toBe('environment_filtering');
    });

    it('should emit onPluginDragStart with type "environment_filtering" when dragged', () => {
      const plugin = makeEnvFilterPlugin();
      fixture.componentRef.setInput('plugins', [plugin]);
      fixture.detectChanges();

      const emitted: {plugin: string; event: Event}[] = [];
      fixture.componentInstance.onPluginDragStart.subscribe(e => emitted.push(e));

      // Expand the application category first
      fixture.componentInstance.expandedCategories.set(new Set(['application']));
      fixture.detectChanges();

      const draggable = fixture.nativeElement.querySelector('[draggable="true"]') as HTMLElement;
      expect(draggable).not.toBeNull();

      // Use a generic Event instead of DragEvent (JSDOM does not include DragEvent)
      const dragEvent = new Event('dragstart', {bubbles: true});
      draggable.dispatchEvent(dragEvent);
      fixture.detectChanges();

      expect(emitted.length).toBe(1);
      expect(emitted[0].plugin).toBe('environment_filtering');
    });
  });

  describe('NodePluginRegistry — application category style', () => {
    it('should produce a plugin with icon=layers_clear for environment_filtering definition', () => {
      // Pure data test: verify that the definitionToPlugin mapping produces
      // the correct icon and category for the application category.
      // (No HTTP, no DI — just validate the mock plugin shape mirrors the registry logic)
      const plugin = makeEnvFilterPlugin();
      expect(plugin.icon).toBe('layers_clear');
      expect(plugin.category).toBe('application');
      expect(plugin.type).toBe('environment_filtering');
    });

    it('should fall back to application style color for application category nodes', () => {
      // When CATEGORY_STYLE['application'] is defined, palette color should be teal
      // This mirrors what node-plugin-registry.service.ts does internally.
      const APPLICATION_COLOR = '#0891b2'; // teal — defined in registry
      const plugin = makeEnvFilterPlugin();
      expect(plugin.style.color).toBe(APPLICATION_COLOR);
    });
  });
});

// ---------------------------------------------------------------------------
// Phase 2 — Status Display (planes_filtered badge)
// ---------------------------------------------------------------------------
describe('Environment Filtering — Phase 2: Status Display', () => {
  let fixture: ComponentFixture<FlowCanvasNodeComponent>;

  const envFilterNode: CanvasNode = {
    id: 'env_filter_1',
    type: 'environment_filtering',
    data: {
      id: 'env_filter_1',
      name: 'Remove Floor/Ceiling',
      type: 'environment_filtering',
      category: 'application',
      enabled: true,
      visible: true,
      config: {
        throttle_ms: 0,
        voxel_downsample_size: 0.01,
        normal_variance_threshold_deg: 60.0,
        coplanarity_deg: 75.0,
        outlier_ratio: 0.75,
        min_plane_edge_length: 0.0,
        min_num_points: 0,
        knn: 30,
        vertical_tolerance_deg: 15.0,
        floor_height_min: -0.5,
        floor_height_max: 0.5,
        ceiling_height_min: 2.0,
        ceiling_height_max: 4.0,
        min_plane_area: 1.0,
      },
      x: 200,
      y: 150,
    },
    position: {x: 200, y: 150},
  };

  beforeEach(async () => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    await TestBed.configureTestingModule({
      imports: [FlowCanvasNodeComponent],
      providers: [NodeStoreService],
    }).compileComponents();

    fixture = TestBed.createComponent(FlowCanvasNodeComponent);
    const nodeStore = TestBed.inject(NodeStoreService);
    nodeStore.set('nodeDefinitions', [MOCK_ENV_FILTER_DEFINITION]);

    fixture.componentRef.setInput('node', envFilterNode);
  });

  it('should render planes_filtered badge with value N and color blue (active state)', () => {
    const status: NodeStatusUpdate = {
      node_id: 'env_filter_1',
      operational_state: 'RUNNING',
      application_state: {label: 'planes_filtered', value: 2, color: 'blue'},
      timestamp: Date.now() / 1000,
    };

    fixture.componentRef.setInput('status', status);
    fixture.detectChanges();

    const badge = (fixture.componentInstance as any)['appBadge']();
    expect(badge).not.toBeNull();
    expect(badge.text).toBe('planes_filtered: 2');
    expect(badge.color).toBe('#2563eb'); // blue hex
  });

  it('should render planes_filtered badge with value 0 and color orange (warning state)', () => {
    const status: NodeStatusUpdate = {
      node_id: 'env_filter_1',
      operational_state: 'RUNNING',
      application_state: {label: 'planes_filtered', value: 0, color: 'orange'},
      timestamp: Date.now() / 1000,
    };

    fixture.componentRef.setInput('status', status);
    fixture.detectChanges();

    const badge = (fixture.componentInstance as any)['appBadge']();
    expect(badge).not.toBeNull();
    expect(badge.text).toBe('planes_filtered: 0');
    expect(badge.color).toBe('#d97706'); // orange hex
  });

  it('should render error section and red operational icon for ERROR state', () => {
    const status: NodeStatusUpdate = {
      node_id: 'env_filter_1',
      operational_state: 'ERROR',
      application_state: {label: 'error', value: 'invalid params: knn must be >= 5', color: 'red'},
      error_message: 'invalid params: knn must be >= 5',
      timestamp: Date.now() / 1000,
    };

    fixture.componentRef.setInput('status', status);
    fixture.detectChanges();

    // Operational icon should be 'error'
    const icon = (fixture.componentInstance as any)['operationalIcon']();
    expect(icon.icon).toBe('error');
    expect(icon.css).toContain('text-syn-color-danger-600');

    // Error text should be shown
    const errorText = (fixture.componentInstance as any)['errorText']();
    expect(errorText).toBe('invalid params: knn must be >= 5');
  });

  it('should render gray idle badge when processing=false (no recent input)', () => {
    const status: NodeStatusUpdate = {
      node_id: 'env_filter_1',
      operational_state: 'RUNNING',
      application_state: {label: 'processing', value: false, color: 'gray'},
      timestamp: Date.now() / 1000,
    };

    fixture.componentRef.setInput('status', status);
    fixture.detectChanges();

    const badge = (fixture.componentInstance as any)['appBadge']();
    expect(badge).not.toBeNull();
    expect(badge.text).toBe('processing: false');
    expect(badge.color).toBe('#6b7280'); // gray hex
  });

  it('should show visibility toggle (websocket_enabled=true)', () => {
    fixture.componentRef.setInput('status', null);
    fixture.detectChanges();

    const isWsEnabled = (fixture.componentInstance as any)['isWebsocketEnabled']();
    expect(isWsEnabled).toBe(true);
  });

  it('should show input port and output port (both defined)', () => {
    fixture.detectChanges();

    const hasInput = (fixture.componentInstance as any)['hasInputPort']();
    const hasOutput = (fixture.componentInstance as any)['hasOutputPort']();

    expect(hasInput).toBe(true);
    expect(hasOutput).toBe(true);
  });

  it('should resolve icon to layers_clear from node definition', () => {
    fixture.detectChanges();

    const icon = fixture.componentInstance.getNodeIcon();
    expect(icon).toBe('layers_clear');
  });
});

// ---------------------------------------------------------------------------
// Phase 3 — Config Panel: voxel_downsample_size property validation
// ---------------------------------------------------------------------------
describe('Environment Filtering — Phase 3: Config Properties', () => {

  it('should have voxel_downsample_size with min=0.0, max=1.0, step=0.005, default=0.01', () => {
    const voxelProp = MOCK_ENV_FILTER_DEFINITION.properties.find(
      p => p.name === 'voxel_downsample_size',
    );
    expect(voxelProp).toBeDefined();
    expect(voxelProp!.min).toBe(0.0);
    expect(voxelProp!.max).toBe(1.0);
    expect(voxelProp!.step).toBe(0.005);
    expect(voxelProp!.default).toBe(0.01);
    expect(voxelProp!.type).toBe('number');
    expect(voxelProp!.help_text).toBeTruthy();
  });

  it('should have all 14 properties including all Group A, B and C fields', () => {
    const props = MOCK_ENV_FILTER_DEFINITION.properties;

    // Group A
    expect(props.find(p => p.name === 'throttle_ms')).toBeDefined();
    expect(props.find(p => p.name === 'voxel_downsample_size')).toBeDefined();

    // Group B
    expect(props.find(p => p.name === 'normal_variance_threshold_deg')).toBeDefined();
    expect(props.find(p => p.name === 'coplanarity_deg')).toBeDefined();
    expect(props.find(p => p.name === 'outlier_ratio')).toBeDefined();
    expect(props.find(p => p.name === 'min_plane_edge_length')).toBeDefined();
    expect(props.find(p => p.name === 'min_num_points')).toBeDefined();
    expect(props.find(p => p.name === 'knn')).toBeDefined();

    // Group C
    expect(props.find(p => p.name === 'vertical_tolerance_deg')).toBeDefined();
    expect(props.find(p => p.name === 'floor_height_min')).toBeDefined();
    expect(props.find(p => p.name === 'floor_height_max')).toBeDefined();
    expect(props.find(p => p.name === 'ceiling_height_min')).toBeDefined();
    expect(props.find(p => p.name === 'ceiling_height_max')).toBeDefined();
    expect(props.find(p => p.name === 'min_plane_area')).toBeDefined();
  });

  it('should have all number-type properties with step defined', () => {
    const props = MOCK_ENV_FILTER_DEFINITION.properties;
    props.forEach(prop => {
      expect(prop.type).toBe('number');
      expect(prop.step).toBeDefined();
      expect(typeof prop.step).toBe('number');
    });
  });

  it('should have default values matching api-spec.md DAG config defaults', () => {
    const defaults: Record<string, number> = {
      throttle_ms: 0,
      voxel_downsample_size: 0.01,
      normal_variance_threshold_deg: 60.0,
      coplanarity_deg: 75.0,
      outlier_ratio: 0.75,
      min_plane_edge_length: 0.0,
      min_num_points: 0,
      knn: 30,
      vertical_tolerance_deg: 15.0,
      floor_height_min: -0.5,
      floor_height_max: 0.5,
      ceiling_height_min: 2.0,
      ceiling_height_max: 4.0,
      min_plane_area: 1.0,
    };

    MOCK_ENV_FILTER_DEFINITION.properties.forEach(prop => {
      expect(prop.default).toBe(defaults[prop.name]);
    });
  });
});
