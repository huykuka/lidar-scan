import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ComponentRef } from '@angular/core';
import { IfConditionCardComponent } from './if-condition-card.component';
import { CanvasNode } from '@features/settings/components/flow-canvas/node/flow-canvas-node.component';
import { IfNodeStatus } from '@core/models/flow-control.model';

describe('IfConditionCardComponent', () => {
  let component: IfConditionCardComponent;
  let componentRef: ComponentRef<IfConditionCardComponent>;
  let fixture: ComponentFixture<IfConditionCardComponent>;

  const mockNode: CanvasNode = {
    id: 'node-1',
    name: 'Test IF Node',
    type: 'if_condition',
    x: 100,
    y: 100,
    data: {
      config: {
        expression: 'point_count > 1000',
        throttle_ms: 0,
      },
    },
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [IfConditionCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(IfConditionCardComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    componentRef.setInput('node', mockNode);
    componentRef.setInput('status', null);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should implement NodeCardComponent interface', () => {
    // Verify the component has required inputs for NodeCardComponent interface
    expect(component.node).toBeDefined();
    expect(component.status).toBeDefined();
  });

  it('should render expression truncated at 30 chars', () => {
    const longExpression = 'point_count > 1000 && density < 50 && quality > 0.8';
    const nodeWithLongExpr: CanvasNode = {
      ...mockNode,
      data: {
        config: {
          expression: longExpression,
        },
      },
    };
    
    componentRef.setInput('node', nodeWithLongExpr);
    fixture.detectChanges();

    const shortExpr = component['shortExpression']();
    expect(shortExpr.length).toBeLessThanOrEqual(30);
    expect(shortExpr).toBe(longExpression.substring(0, 27) + '...');
  });

  it('should not truncate short expressions', () => {
    const shortExpression = 'true';
    const nodeWithShortExpr: CanvasNode = {
      ...mockNode,
      data: {
        config: {
          expression: shortExpression,
        },
      },
    };
    
    componentRef.setInput('node', nodeWithShortExpr);
    fixture.detectChanges();

    const shortExpr = component['shortExpression']();
    expect(shortExpr).toBe(shortExpression);
  });

  it('should show TRUE badge when last_evaluation=true', () => {
    const status: IfNodeStatus = {
      node_id: 'node-1',
      name: 'Test IF Node',
      type: 'if_condition',
      status: 'active',
      config: {
        expression: 'point_count > 1000',
        throttle_ms: 0,
      },
      last_evaluation: true,
      external_state: null,
      last_error: null,
    };

    componentRef.setInput('status', status);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const badge = compiled.querySelector('syn-badge');
    expect(badge).toBeTruthy();
    expect(badge?.textContent?.trim()).toContain('TRUE');
  });

  it('should show FALSE badge when last_evaluation=false', () => {
    const status: IfNodeStatus = {
      node_id: 'node-1',
      name: 'Test IF Node',
      type: 'if_condition',
      status: 'active',
      config: {
        expression: 'point_count > 1000',
        throttle_ms: 0,
      },
      last_evaluation: false,
      external_state: null,
      last_error: null,
    };

    componentRef.setInput('status', status);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const badge = compiled.querySelector('syn-badge');
    expect(badge).toBeTruthy();
    expect(badge?.textContent?.trim()).toContain('FALSE');
  });

  it('should show "Ext: ON" badge when external_state=true', () => {
    const status: IfNodeStatus = {
      node_id: 'node-1',
      name: 'Test IF Node',
      type: 'if_condition',
      status: 'active',
      config: {
        expression: 'point_count > 1000',
        throttle_ms: 0,
      },
      last_evaluation: true,
      external_state: true,
      last_error: null,
    };

    componentRef.setInput('status', status);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent || '';
    expect(text).toContain('Ext: ON');
  });

  it('should show error badge when last_error present', () => {
    const status: IfNodeStatus = {
      node_id: 'node-1',
      name: 'Test IF Node',
      type: 'if_condition',
      status: 'error',
      config: {
        expression: 'invalid expression',
        throttle_ms: 0,
      },
      last_evaluation: null,
      external_state: null,
      last_error: 'Syntax error in expression',
    };

    componentRef.setInput('status', status);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent || '';
    expect(text).toContain('Error');
  });

  it('should handle null status gracefully', () => {
    componentRef.setInput('status', null);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled).toBeTruthy();
    // Should render without errors
  });

  it('should use default expression "true" when config missing', () => {
    const nodeNoConfig: CanvasNode = {
      ...mockNode,
      data: {
        config: undefined,
      },
    };
    
    componentRef.setInput('node', nodeNoConfig);
    fixture.detectChanges();

    const shortExpr = component['shortExpression']();
    expect(shortExpr).toBe('true');
  });
});
