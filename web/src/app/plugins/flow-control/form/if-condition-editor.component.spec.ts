// @ts-nocheck
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ComponentRef, signal } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { IfConditionEditorComponent } from './if-condition-editor.component';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorFacadeService } from '@features/settings/services/node-editor-facade.service';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

describe('IfConditionEditorComponent', () => {
  let component: IfConditionEditorComponent;
  let componentRef: ComponentRef<IfConditionEditorComponent>;
  let fixture: ComponentFixture<IfConditionEditorComponent>;
  let nodeStoreService: jasmine.SpyObj<NodeStoreService>;
  let toastService: jasmine.SpyObj<ToastService>;

  const mockNode = {
    id: 'node-1',
    type: 'if_condition',
    name: 'Test IF Node',
    config: {
      expression: 'point_count > 1000',
      throttle_ms: 0,
      use_external_control: false,
    },
    enabled: true,
  };

  beforeEach(async () => {
    const nodeStoreSpy = jasmine.createSpyObj('NodeStoreService', [
      'selectedNode',
      'select',
      'setState',
    ]);
    const toastSpy = jasmine.createSpyObj('ToastService', [
      'success',
      'warning',
      'danger',
    ]);

    // Setup node store spy to return signals
    nodeStoreSpy.selectedNode = signal(mockNode);
    nodeStoreSpy.select = jasmine.createSpy('select').and.returnValue(signal(false));

    await TestBed.configureTestingModule({
      imports: [IfConditionEditorComponent, ReactiveFormsModule],
      providers: [
        { provide: NodeStoreService, useValue: nodeStoreSpy },
        { provide: ToastService, useValue: toastSpy },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    nodeStoreService = TestBed.inject(NodeStoreService) as jasmine.SpyObj<NodeStoreService>;
    toastService = TestBed.inject(ToastService) as jasmine.SpyObj<ToastService>;

    fixture = TestBed.createComponent(IfConditionEditorComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should implement NodeEditorComponent interface', () => {
    // Verify component has required outputs
    expect(component.saved).toBeDefined();
    expect(component.cancelled).toBeDefined();
  });

  it('should initialize form with node data', () => {
    expect(component.form.get('name')?.value).toBe('Test IF Node');
    expect(component.form.get('expression')?.value).toBe('point_count > 1000');
    expect(component.form.get('use_external_control')?.value).toBe(false);
  });

  it('should default to "If Condition" name when node has no name', () => {
    const nodeWithoutName = { ...mockNode, name: undefined };
    nodeStoreService.selectedNode = signal(nodeWithoutName);
    
    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();
    
    expect(newFixture.componentInstance.form.get('name')?.value).toBe('If Condition');
  });

  it('should default to "true" expression when node has no expression', () => {
    const nodeWithoutExpr = { ...mockNode, config: {} };
    nodeStoreService.selectedNode = signal(nodeWithoutExpr);
    
    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();
    
    expect(newFixture.componentInstance.form.get('expression')?.value).toBe('true');
  });

  it('should validate expression with allowed characters', () => {
    const expressionControl = component.form.get('expression');
    
    expressionControl?.setValue('point_count > 1000');
    expect(component['validationError']()).toBeNull();
    
    expressionControl?.setValue('point_count > 1000 AND density < 50');
    expect(component['validationError']()).toBeNull();
    
    expressionControl?.setValue('invalid$character');
    expect(component['validationError']()).toBe('Invalid characters in expression');
  });

  it('should detect unbalanced parentheses', () => {
    const expressionControl = component.form.get('expression');
    
    expressionControl?.setValue('(point_count > 1000');
    expect(component['validationError']()).toBe('Unbalanced parentheses');
    
    expressionControl?.setValue('point_count > 1000)');
    expect(component['validationError']()).toBe('Unbalanced parentheses');
    
    expressionControl?.setValue('(point_count > 1000) AND (density < 50)');
    expect(component['validationError']()).toBeNull();
  });

  it('should show validation error for empty expression', () => {
    const expressionControl = component.form.get('expression');
    
    expressionControl?.setValue('');
    expect(component['validationError']()).toBe('Expression cannot be empty');
    
    expressionControl?.setValue('   ');
    expect(component['validationError']()).toBe('Expression cannot be empty');
  });

  it('should emit saved event on valid form submit', () => {
    let savedEmitted = false;
    component.saved.subscribe(() => {
      savedEmitted = true;
    });

    component.form.patchValue({
      name: 'Updated Node',
      expression: 'point_count > 2000',
      use_external_control: true,
    });

    component.onSave();

    expect(savedEmitted).toBe(true);
    expect(nodeStoreService.setState).toHaveBeenCalledWith({
      selectedNode: jasmine.objectContaining({
        name: 'Updated Node',
        config: jasmine.objectContaining({
          expression: 'point_count > 2000',
          throttle_ms: 0,
          use_external_control: true,
        }),
      }),
    });
  });

  it('should always save throttle_ms as 0', () => {
    component.form.patchValue({
      name: 'Test Node',
      expression: 'true',
      use_external_control: false,
    });

    component.onSave();

    expect(nodeStoreService.setState).toHaveBeenCalledWith({
      selectedNode: jasmine.objectContaining({
        config: jasmine.objectContaining({
          throttle_ms: 0,
        }),
      }),
    });
  });

  it('should not save if form is invalid', () => {
    component.form.get('expression')?.setValue('');
    component.onSave();

    expect(toastService.warning).toHaveBeenCalledWith('Please fix validation errors before saving');
    expect(nodeStoreService.setState).not.toHaveBeenCalled();
  });

  it('should emit cancelled event on cancel', () => {
    let cancelledEmitted = false;
    component.cancelled.subscribe(() => {
      cancelledEmitted = true;
    });

    component.onCancel();

    expect(cancelledEmitted).toBe(true);
  });

  it('should copy URL to clipboard', async () => {
    const testUrl = 'http://test.com/api';
    spyOn(navigator.clipboard, 'writeText').and.returnValue(Promise.resolve());

    await component['copyToClipboard'](testUrl);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(testUrl);
    expect(toastService.success).toHaveBeenCalledWith('URL copied to clipboard');
  });

  it('should show error toast on clipboard failure', async () => {
    const testUrl = 'http://test.com/api';
    spyOn(navigator.clipboard, 'writeText').and.returnValue(Promise.reject('Error'));
    spyOn(console, 'error');

    await component['copyToClipboard'](testUrl);

    expect(toastService.danger).toHaveBeenCalledWith('Failed to copy to clipboard');
  });

  it('should show external URLs only when editing existing node', () => {
    // New node (not editing)
    nodeStoreService.select = jasmine.createSpy('select').and.returnValue(signal(false));
    expect(component['isEditMode']()).toBe(false);
    
    // Existing node (editing)
    nodeStoreService.select = jasmine.createSpy('select').and.returnValue(signal(true));
    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();
    
    expect(newFixture.componentInstance['isEditMode']()).toBe(true);
  });

  it('should compute set and reset URLs when node has ID', () => {
    const nodeWithId = { ...mockNode, id: 'node-123' };
    nodeStoreService.selectedNode = signal(nodeWithId);
    
    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();
    
    const setUrl = newFixture.componentInstance['setUrl']();
    const resetUrl = newFixture.componentInstance['resetUrl']();
    
    expect(setUrl).toContain('/nodes/node-123/flow-control/set');
    expect(resetUrl).toContain('/nodes/node-123/flow-control/reset');
  });

  it('should return null URLs when node has no ID', () => {
    const nodeWithoutId = { ...mockNode, id: null };
    nodeStoreService.selectedNode = signal(nodeWithoutId);
    
    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();
    
    expect(newFixture.componentInstance['setUrl']()).toBeNull();
    expect(newFixture.componentInstance['resetUrl']()).toBeNull();
  });

  it('should unsubscribe from expression changes on destroy', () => {
    const unsubscribeSpy = jasmine.createSpy('unsubscribe');
    component['expressionSub'] = { unsubscribe: unsubscribeSpy } as any;
    
    component.ngOnDestroy();
    
    expect(unsubscribeSpy).toHaveBeenCalled();
  });
});
