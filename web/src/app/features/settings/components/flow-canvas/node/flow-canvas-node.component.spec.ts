import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FlowCanvasNodeComponent, CanvasNode } from './flow-canvas-node.component';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { NodeStatusUpdate } from '@core/models/node-status.model';
import { signal } from '@angular/core';

describe('FlowCanvasNodeComponent', () => {
  let component: FlowCanvasNodeComponent;
  let fixture: ComponentFixture<FlowCanvasNodeComponent>;
  let mockNodeStore: jasmine.SpyObj<NodeStoreService>;

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
      config: {}
    },
    position: { x: 100, y: 100 }
  };

  beforeEach(async () => {
    mockNodeStore = jasmine.createSpyObj('NodeStoreService', [], {
      definitions: signal([
        {
          type: 'crop',
          category: 'operation',
          name: 'Crop Filter',
          description: 'Test node',
          inputs: [{ id: 'in', type: 'PointCloud' }],
          outputs: [{ id: 'out', type: 'PointCloud' }],
          properties: []
        }
      ])
    });

    await TestBed.configureTestingModule({
      imports: [FlowCanvasNodeComponent],
      providers: [
        { provide: NodeStoreService, useValue: mockNodeStore }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(FlowCanvasNodeComponent);
    component = fixture.componentInstance;
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
        expect(badge?.color).toBe(hex, `Expected ${name} to map to ${hex}`);
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
});
