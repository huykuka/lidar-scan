// @ts-nocheck
import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ComponentRef, signal} from '@angular/core';
import {ReactiveFormsModule} from '@angular/forms';
import {IfConditionEditorComponent} from './if-condition-editor.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {ToastService} from '@core/services/toast.service';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';

describe('IfConditionEditorComponent', () => {
  let component: IfConditionEditorComponent;
  let componentRef: ComponentRef<IfConditionEditorComponent>;
  let fixture: ComponentFixture<IfConditionEditorComponent>;
  let nodeStoreSpy: ReturnType<typeof createNodeStoreMock>;
  let toastSpy: ReturnType<typeof createToastMock>;
  let facadeSpy: ReturnType<typeof createFacadeMock>;

  // jsdom does not implement navigator.clipboard — polyfill it for these tests
  beforeAll(() => {
    if (!navigator.clipboard) {
      Object.defineProperty(navigator, 'clipboard', {
        value: {writeText: vi.fn()},
        configurable: true,
        writable: true,
      });
    }
  });

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

  function createNodeStoreMock(node = mockNode) {
    return {
      selectedNode: signal(node),
      nodeDefinitions: signal([{type: 'if_condition', category: 'operation', properties: []}]),
      select: vi.fn().mockReturnValue(signal(false)),
      setState: vi.fn(),
    };
  }

  function createToastMock() {
    return {
      success: vi.fn(),
      warning: vi.fn(),
      danger: vi.fn(),
    };
  }

  function createFacadeMock() {
    return {
      saveNode: vi.fn().mockResolvedValue(true),
    };
  }

  async function buildTestBed(nodeStoreMock = createNodeStoreMock(), facadeMock = createFacadeMock(), toastMock = createToastMock()) {
    // The component declares `providers: [NodeEditorFacadeService]`, so TestBed-level
    // `useValue` overrides are ignored. We must use overrideComponent() to replace the
    // component-level provider with our mock.
    await TestBed.configureTestingModule({
      imports: [IfConditionEditorComponent, ReactiveFormsModule],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: ToastService, useValue: toastMock},
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    })
      .overrideComponent(IfConditionEditorComponent, {
        set: {
          providers: [{provide: NodeEditorFacadeService, useValue: facadeMock}],
        },
      })
      .compileComponents();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    nodeStoreSpy = createNodeStoreMock();
    toastSpy = createToastMock();
    facadeSpy = createFacadeMock();

    await buildTestBed(nodeStoreSpy, facadeSpy, toastSpy);

    fixture = TestBed.createComponent(IfConditionEditorComponent);
    component = fixture.componentInstance;
    componentRef = fixture.componentRef;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should implement NodeEditorComponent interface', () => {
    expect(component.saved).toBeDefined();
    expect(component.cancelled).toBeDefined();
  });

  it('should initialize form with node data', () => {
    expect(component.form.get('name')?.value).toBe('Test IF Node');
    expect(component.form.get('expression')?.value).toBe('point_count > 1000');
    expect(component.form.get('use_external_control')?.value).toBe(false);
  });

  it('should default to "If Condition" name when node has no name', async () => {
    TestBed.resetTestingModule();
    const nodeWithoutName = {...mockNode, name: undefined};
    const localStoreMock = createNodeStoreMock(nodeWithoutName);

    await buildTestBed(localStoreMock);

    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();

    expect(newFixture.componentInstance.form.get('name')?.value).toBe('If Condition');
  });

  it('should default to "true" expression when node has no expression', async () => {
    TestBed.resetTestingModule();
    const nodeWithoutExpr = {...mockNode, config: {}};
    const localStoreMock = createNodeStoreMock(nodeWithoutExpr);

    await buildTestBed(localStoreMock);

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

  it('should emit saved event on valid form submit', async () => {
    let savedEmitted = false;
    component.saved.subscribe(() => {
      savedEmitted = true;
    });

    component.form.patchValue({
      name: 'Updated Node',
      expression: 'point_count > 2000',
      use_external_control: true,
    });

    await component.onSave();

    expect(savedEmitted).toBe(true);
    expect(facadeSpy.saveNode).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Updated Node',
        config: expect.objectContaining({
          expression: 'point_count > 2000',
          throttle_ms: 0,
          use_external_control: true,
        }),
      }),
    );
  });

  it('should always save throttle_ms as 0', async () => {
    component.form.patchValue({
      name: 'Test Node',
      expression: 'true',
      use_external_control: false,
    });

    await component.onSave();

    expect(facadeSpy.saveNode).toHaveBeenCalledWith(
      expect.objectContaining({
        config: expect.objectContaining({
          throttle_ms: 0,
        }),
      }),
    );
  });

  it('should not save if form is invalid', async () => {
    component.form.get('expression')?.setValue('');
    await component.onSave();

    expect(toastSpy.warning).toHaveBeenCalledWith('Please fix validation errors before saving');
    expect(facadeSpy.saveNode).not.toHaveBeenCalled();
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
    const clipboardSpy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);

    await component['copyToClipboard'](testUrl);

    expect(clipboardSpy).toHaveBeenCalledWith(testUrl);
    expect(toastSpy.success).toHaveBeenCalledWith('URL copied to clipboard');
  });

  it('should show error toast on clipboard failure', async () => {
    const testUrl = 'http://test.com/api';
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('fail'));
    vi.spyOn(console, 'error').mockImplementation(() => {});

    await component['copyToClipboard'](testUrl);

    expect(toastSpy.danger).toHaveBeenCalledWith('Failed to copy to clipboard');
  });

  it('should show external URLs only when editing existing node', () => {
    expect(component['isEditMode']()).toBe(false);
  });

  it('should compute set and reset URLs when node has ID', async () => {
    TestBed.resetTestingModule();
    const nodeWithId = {...mockNode, id: 'node-123'};
    const localStoreMock = {
      selectedNode: signal(nodeWithId),
      nodeDefinitions: signal([{type: 'if_condition', category: 'operation', properties: []}]),
      select: vi.fn().mockReturnValue(signal(true)),
      setState: vi.fn(),
    };

    await buildTestBed(localStoreMock);

    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();

    const setUrl = newFixture.componentInstance['setUrl']();
    const resetUrl = newFixture.componentInstance['resetUrl']();

    expect(setUrl).toContain('/nodes/node-123/flow-control/set');
    expect(resetUrl).toContain('/nodes/node-123/flow-control/reset');
  });

  it('should return null URLs when node has no ID', async () => {
    TestBed.resetTestingModule();
    const nodeWithoutId = {...mockNode, id: null};
    const localStoreMock = createNodeStoreMock(nodeWithoutId);

    await buildTestBed(localStoreMock);

    const newFixture = TestBed.createComponent(IfConditionEditorComponent);
    newFixture.detectChanges();

    expect(newFixture.componentInstance['setUrl']()).toBeNull();
    expect(newFixture.componentInstance['resetUrl']()).toBeNull();
  });

  it('should unsubscribe from expression changes on destroy', () => {
    const unsubscribeFn = vi.fn();
    component['expressionSub'] = {unsubscribe: unsubscribeFn} as any;

    component.ngOnDestroy();

    expect(unsubscribeFn).toHaveBeenCalled();
  });
});
