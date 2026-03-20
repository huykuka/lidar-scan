import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FlowCanvasNodeComponent, CanvasNode } from './flow-canvas-node.component';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { NodeDefinition } from '@core/models/node.model';
import { signal, Signal } from '@angular/core';
import { By } from '@angular/platform-browser';

describe('FlowCanvasNodeComponent', () => {
  let component: FlowCanvasNodeComponent;
  let fixture: ComponentFixture<FlowCanvasNodeComponent>;
  let nodeStore: NodeStoreService;

  const mockNode: CanvasNode = {
    id: 'test-node-id',
    type: 'crop',
    data: {
      id: 'test-node-id',
      name: 'Test Node',
      type: 'crop',
      category: 'operation',
      enabled: true,
      visible: true,
      config: {},
      x: 0,
      y: 0
    },
    position: { x: 100, y: 100 }
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FlowCanvasNodeComponent],
      providers: [NodeStoreService]
    }).compileComponents();

    fixture = TestBed.createComponent(FlowCanvasNodeComponent);
    component = fixture.componentInstance;
    nodeStore = TestBed.inject(NodeStoreService);
    
    // Initialize with empty state
    nodeStore.set('nodeDefinitions', []);
    
    fixture.componentRef.setInput('node', mockNode);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Operational State Icons', () => {
    it('should display hourglass_empty icon with animate-pulse for INITIALIZE', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'INITIALIZE',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const icon = component['operationalIcon']();
      expect(icon.icon).toBe('hourglass_empty');
      expect(icon.css).toContain('animate-pulse');
      expect(icon.css).toContain('text-syn-color-warning-600');
    });

    it('should display play_circle icon for RUNNING', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const icon = component['operationalIcon']();
      expect(icon.icon).toBe('play_circle');
      expect(icon.css).toBe('text-syn-color-success-600');
    });

    it('should display pause_circle icon for STOPPED', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'STOPPED',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const icon = component['operationalIcon']();
      expect(icon.icon).toBe('pause_circle');
      expect(icon.css).toBe('text-syn-color-neutral-400');
    });

    it('should display error icon for ERROR', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'ERROR',
        error_message: 'Test error',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const icon = component['operationalIcon']();
      expect(icon.icon).toBe('error');
      expect(icon.css).toBe('text-syn-color-danger-600');
    });
  });

  describe('Application State Badge', () => {
    it('should render application state badge when application_state is present', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        application_state: {
          label: 'processing',
          value: true,
          color: 'blue'
        },
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const badge = component['appBadge']();
      expect(badge).not.toBeNull();
      expect(badge?.text).toBe('processing: true');
      expect(badge?.color).toBe('#2563eb'); // blue hex
    });

    it('should NOT render badge when application_state is absent', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const badge = component['appBadge']();
      expect(badge).toBeNull();
    });

    it('should apply correct hex color from badgeColorMap for each named color', () => {
      const colors: Array<{ name: 'green' | 'blue' | 'orange' | 'red' | 'gray'; hex: string }> = [
        { name: 'green', hex: '#16a34a' },
        { name: 'blue', hex: '#2563eb' },
        { name: 'orange', hex: '#d97706' },
        { name: 'red', hex: '#dc2626' },
        { name: 'gray', hex: '#6b7280' }
      ];

      colors.forEach(({ name, hex }) => {
        const status: NodeStatusUpdate = {
          node_id: 'test-node-id',
          operational_state: 'RUNNING',
          application_state: {
            label: 'test',
            value: 'test',
            color: name
          },
          timestamp: Date.now() / 1000
        };
        
        fixture.componentRef.setInput('status', status);
        fixture.detectChanges();
        
        const badge = component['appBadge']();
        expect(badge?.color).toBe(hex);
      });
    });

    it('should fall back to gray hex when application_state.color is undefined', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        application_state: {
          label: 'test',
          value: 'test'
          // color is undefined
        },
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const badge = component['appBadge']();
      expect(badge?.color).toBe('#6b7280'); // gray fallback
    });

    it('should render Node-RED style label: colored square on left, muted text, no border/pill', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        application_state: { label: 'connected', value: true, color: 'green' },
        timestamp: Date.now() / 1000,
      };
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      // Container must be absolute, anchored bottom-left, no border class
      const container = compiled.querySelector<HTMLElement>('div[class*="-bottom-5"]');
      expect(container).toBeTruthy();
      expect(container!.classList.contains('absolute')).toBe(true);
      expect(container!.classList.contains('left-0')).toBe(true);
      expect(container!.classList.contains('rounded-full')).toBe(false);
      expect(container!.classList.contains('border')).toBe(false);

      // First child: square indicator (no rounded-full)
      const square = container!.children[0] as HTMLElement;
      expect(square.classList.contains('rounded-full')).toBe(false);
      expect(square.style.backgroundColor).toBe('rgb(22, 163, 74)'); // #16a34a

      // Second child: text in muted gray
      const label = container!.children[1] as HTMLElement;
      expect(label.textContent?.trim()).toBe('connected: true');
      expect(label.classList.contains('text-gray-500')).toBe(true);
    });

    it('should format boolean value as "true"/"false" string in badge text', () => {
      const trueStatus: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        application_state: {
          label: 'processing',
          value: true,
          color: 'blue'
        },
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', trueStatus);
      fixture.detectChanges();
      
      let badge = component['appBadge']();
      expect(badge?.text).toBe('processing: true');

      const falseStatus: NodeStatusUpdate = {
        ...trueStatus,
        application_state: {
          label: 'processing',
          value: false,
          color: 'gray'
        }
      };
      
      fixture.componentRef.setInput('status', falseStatus);
      fixture.detectChanges();
      
      badge = component['appBadge']();
      expect(badge?.text).toBe('processing: false');
    });
  });

  describe('Error Message Display', () => {
    it('should display error text in body when operational_state is ERROR', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'ERROR',
        error_message: 'Test error message',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const errorText = component['errorText']();
      expect(errorText).toBe('Test error message');
    });

    it('should NOT display error text when operational_state is RUNNING', () => {
      const status: NodeStatusUpdate = {
        node_id: 'test-node-id',
        operational_state: 'RUNNING',
        timestamp: Date.now() / 1000
      };
      
      fixture.componentRef.setInput('status', status);
      fixture.detectChanges();
      
      const errorText = component['errorText']();
      expect(errorText).toBeNull();
    });
  });

  describe('WebSocket Enabled Behavior', () => {
    it('should hide visibility toggle when websocket_enabled is false', () => {
      // Arrange: Mock node definition with websocket_enabled=false
      const mockDefinition: NodeDefinition = {
        type: 'calibration',
        display_name: 'ICP Calibration',
        category: 'calibration',
        icon: 'tune',
        websocket_enabled: false,
        properties: [],
        inputs: [],
        outputs: []
      };
      nodeStore.set('nodeDefinitions', [mockDefinition]);

      // Act: Set node data and detect changes
      const node: CanvasNode = {
        id: 'cal-1',
        type: 'calibration',
        data: { 
          id: 'cal-1',
          type: 'calibration', 
          name: 'Test Calibration',
          category: 'calibration',
          enabled: true, 
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      // Assert: Visibility toggle should not be rendered
      const visibilityToggle = fixture.debugElement.query(
        By.css('app-node-visibility-toggle')
      );
      expect(visibilityToggle).toBeNull();
    });

    it('should hide recording controls when websocket_enabled is false', () => {
      // Arrange: Mock flow control node with outputs but no websocket
      const mockDefinition: NodeDefinition = {
        type: 'if_condition',
        display_name: 'If Condition',
        category: 'flow_control',
        icon: 'call_split',
        websocket_enabled: false,
        properties: [],
        inputs: [{ id: 'in', label: 'Input', data_type: 'pointcloud', multiple: false }],
        outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
      };
      nodeStore.set('nodeDefinitions', [mockDefinition]);

      const node: CanvasNode = {
        id: 'if-1',
        type: 'if_condition',
        data: {
          id: 'if-1',
          type: 'if_condition',
          name: 'Test If',
          category: 'flow_control',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      // Assert: Recording controls should not be rendered
      const recordingControls = fixture.debugElement.query(
        By.css('app-node-recording-controls')
      );
      expect(recordingControls).toBeNull();
    });

    it('should show visibility toggle when websocket_enabled is true', () => {
      // Arrange: Mock sensor node definition with websocket enabled
      const mockDefinition: NodeDefinition = {
        type: 'sensor',
        display_name: 'LiDAR Sensor',
        category: 'sensor',
        icon: 'sensors',
        websocket_enabled: true,
        properties: [],
        inputs: [],
        outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
      };
      nodeStore.set('nodeDefinitions', [mockDefinition]);

      const node: CanvasNode = {
        id: 'sen-1',
        type: 'sensor',
        data: {
          id: 'sen-1',
          type: 'sensor',
          name: 'Test Sensor',
          category: 'sensor',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      // Assert: Visibility toggle SHOULD be rendered
      const visibilityToggle = fixture.debugElement.query(
        By.css('app-node-visibility-toggle')
      );
      expect(visibilityToggle).not.toBeNull();
    });

    it('should show recording controls when websocket_enabled is true and node has outputs', () => {
      // Arrange: Mock sensor node with outputs and websocket enabled
      const mockDefinition: NodeDefinition = {
        type: 'sensor',
        display_name: 'LiDAR Sensor',
        category: 'sensor',
        icon: 'sensors',
        websocket_enabled: true,
        properties: [],
        inputs: [],
        outputs: [{ id: 'out', label: 'Output', data_type: 'pointcloud', multiple: false }]
      };
      nodeStore.set('nodeDefinitions', [mockDefinition]);

      const node: CanvasNode = {
        id: 'sen-1',
        type: 'sensor',
        data: {
          id: 'sen-1',
          type: 'sensor',
          name: 'Test Sensor',
          category: 'sensor',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      // Assert: Recording controls SHOULD be rendered
      const recordingControls = fixture.debugElement.query(
        By.css('app-node-recording-controls')
      );
      expect(recordingControls).not.toBeNull();
    });

    it('should default to showing controls when definition is missing', () => {
      // Arrange: No definition registered for this type
      nodeStore.set('nodeDefinitions', []);

      const node: CanvasNode = {
        id: 'unknown-1',
        type: 'unknown_type',
        data: {
          id: 'unknown-1',
          type: 'unknown_type',
          name: 'Unknown Node',
          category: 'unknown',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', node);
      fixture.detectChanges();

      // Assert: Controls should be shown (safe default)
      const visibilityToggle = fixture.debugElement.query(
        By.css('app-node-visibility-toggle')
      );
      expect(visibilityToggle).not.toBeNull();
    });

    it('should compute isWebsocketEnabled correctly for various scenarios', () => {
      // Scenario 1: Definition with websocket_enabled=true
      const enabledDef: NodeDefinition = {
        type: 'sensor',
        display_name: 'Sensor',
        category: 'sensor',
        icon: 'sensors',
        websocket_enabled: true,
        properties: [],
        inputs: [],
        outputs: []
      };
      nodeStore.set('nodeDefinitions', [enabledDef]);

      const sensorNode: CanvasNode = {
        id: 'sen-1',
        type: 'sensor',
        data: {
          id: 'sen-1',
          type: 'sensor',
          name: 'Test',
          category: 'sensor',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', sensorNode);
      fixture.detectChanges();

      expect(component['isWebsocketEnabled']()).toBe(true);

      // Scenario 2: Definition with websocket_enabled=false
      const disabledDef: NodeDefinition = {
        type: 'calibration',
        display_name: 'Calibration',
        category: 'calibration',
        icon: 'tune',
        websocket_enabled: false,
        properties: [],
        inputs: [],
        outputs: []
      };
      nodeStore.set('nodeDefinitions', [disabledDef]);

      const calibrationNode: CanvasNode = {
        id: 'cal-1',
        type: 'calibration',
        data: {
          id: 'cal-1',
          type: 'calibration',
          name: 'Test',
          category: 'calibration',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', calibrationNode);
      fixture.detectChanges();

      expect(component['isWebsocketEnabled']()).toBe(false);

      // Scenario 3: No definition found (backward compatibility)
      nodeStore.set('nodeDefinitions', []);

      const unknownNode: CanvasNode = {
        id: 'unknown-1',
        type: 'unknown',
        data: {
          id: 'unknown-1',
          type: 'unknown',
          name: 'Test',
          category: 'unknown',
          enabled: true,
          config: {},
          x: 0,
          y: 0
        },
        position: { x: 0, y: 0 }
      };
      fixture.componentRef.setInput('node', unknownNode);
      fixture.detectChanges();

      expect(component['isWebsocketEnabled']()).toBe(true);
    });
  });
});
