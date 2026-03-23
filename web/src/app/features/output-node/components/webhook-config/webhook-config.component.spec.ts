// @ts-nocheck
import {TestBed} from '@angular/core/testing';
import {CUSTOM_ELEMENTS_SCHEMA} from '@angular/core';
import {WebhookConfigComponent} from './webhook-config.component';
import {OutputNodeApiService} from '@features/output-node/services/output-node-api.service';
import {ToastService} from '@core/services/toast.service';
import {DEFAULT_WEBHOOK_CONFIG, WebhookConfig} from '@core/models/output-node.model';

/**
 * Unit tests for WebhookConfigComponent.
 *
 * TDD tests covering:
 * F5.7: All 11 specified test cases
 */
describe('WebhookConfigComponent', () => {
  let mockApiService: {
    updateWebhookConfig: ReturnType<typeof vi.fn>;
  };
  let mockToast: {
    success: ReturnType<typeof vi.fn>;
    danger: ReturnType<typeof vi.fn>;
    warning: ReturnType<typeof vi.fn>;
  };

  const BEARER_CONFIG: WebhookConfig = {
    webhook_enabled: true,
    webhook_url: 'https://example.com/hook',
    webhook_auth_type: 'bearer',
    webhook_auth_token: 'tok-123',
    webhook_custom_headers: {},
  };

  const BASIC_CONFIG: WebhookConfig = {
    webhook_enabled: true,
    webhook_url: 'https://example.com/hook',
    webhook_auth_type: 'basic',
    webhook_auth_username: 'user',
    webhook_auth_password: 'pass',
    webhook_custom_headers: {},
  };

  const API_KEY_CONFIG: WebhookConfig = {
    webhook_enabled: true,
    webhook_url: 'https://example.com/hook',
    webhook_auth_type: 'api_key',
    webhook_auth_key_name: 'X-API-Key',
    webhook_auth_key_value: 'secret',
    webhook_custom_headers: {},
  };

  beforeEach(async () => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    mockApiService = {
      updateWebhookConfig: vi.fn().mockResolvedValue({status: 'ok', node_id: 'test-node'}),
    };

    mockToast = {
      success: vi.fn(),
      danger: vi.fn(),
      warning: vi.fn(),
    };

    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [WebhookConfigComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [
        {provide: OutputNodeApiService, useValue: mockApiService},
        {provide: ToastService, useValue: mockToast},
      ],
    }).compileComponents();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Toggle behavior
  // ──────────────────────────────────────────────────────────────────────────

  it('hides webhook fields when toggle is off', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {...DEFAULT_WEBHOOK_CONFIG, webhook_enabled: false});
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    // URL input should not be in DOM when disabled
    expect(compiled.querySelector('syn-input[label="Webhook POST URL"]')).toBeNull();
  });

  it('shows webhook fields when toggle is on', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: 'https://example.com',
    });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    // The syn-input has label="Webhook POST URL" as an attribute
    const urlInput = compiled.querySelector('syn-input[label="Webhook POST URL"]');
    expect(urlInput).not.toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Auth type conditional fields
  // ──────────────────────────────────────────────────────────────────────────

  it('shows bearer token input when auth_type is bearer', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    // The Bearer Token input has label="Bearer Token" attribute on syn-input
    expect(compiled.querySelector('syn-input[label="Bearer Token"]')).not.toBeNull();
  });

  it('shows username+password when auth_type is basic', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BASIC_CONFIG);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('syn-input[label="Username"]')).not.toBeNull();
    expect(compiled.querySelector('syn-input[label="Password"]')).not.toBeNull();
  });

  it('shows header name+value when auth_type is api_key', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', API_KEY_CONFIG);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('syn-input[label="Header Name"]')).not.toBeNull();
    expect(compiled.querySelector('syn-input[label="Key Value"]')).not.toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // URL validation
  // ──────────────────────────────────────────────────────────────────────────

  it('shows validation error for empty URL when enabled', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: '',
    });
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.urlValidationError()).not.toBeNull();
  });

  it('shows warning for http URL', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: 'http://example.com/hook',
    });
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.urlWarning()).not.toBeNull();
    expect(comp.urlWarning()).toContain('HTTPS');
  });

  it('disables save button when url is invalid', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: '',
    });
    fixture.detectChanges();

    // The urlValidationError computed signal should return an error
    const comp = fixture.componentInstance as any;
    expect(comp.urlValidationError()).not.toBeNull();

    // Also verify the save button has disabled attribute/property
    const saveBtn = fixture.nativeElement.querySelector('syn-button[variant="filled"]');
    expect(saveBtn).toBeDefined();
    // Angular sets disabled as a DOM property on the web component
    const isDisabled =
      saveBtn?.hasAttribute('disabled') || (saveBtn as any)?.disabled === true;
    expect(isDisabled).toBe(true);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Save handler
  // ──────────────────────────────────────────────────────────────────────────

  it('calls updateWebhookConfig on save', async () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.componentRef.setInput('nodeId', 'test-node-id');
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    await comp.onSave();

    expect(mockApiService.updateWebhookConfig).toHaveBeenCalledWith(
      'test-node-id',
      expect.objectContaining({webhook_enabled: true}),
    );
  });

  it('does not call API when validation error is present', async () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: '', // invalid
    });
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    await comp.onSave();

    expect(mockApiService.updateWebhookConfig).not.toHaveBeenCalled();
  });

  it('shows success toast after successful save', async () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.componentRef.setInput('nodeId', 'test-node');
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    await comp.onSave();

    expect(mockToast.success).toHaveBeenCalled();
  });

  it('shows error toast on failed save', async () => {
    mockApiService.updateWebhookConfig.mockRejectedValue(new Error('Network error'));

    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.componentRef.setInput('nodeId', 'test-node');
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    await comp.onSave();

    expect(mockToast.danger).toHaveBeenCalled();
  });

  it('emits webhookSaved event on successful save', async () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.componentRef.setInput('nodeId', 'test-node');
    fixture.detectChanges();

    const comp = fixture.componentInstance;
    const savedValues: WebhookConfig[] = [];
    comp.webhookSaved.subscribe((v: WebhookConfig) => savedValues.push(v));

    await (comp as any).onSave();

    expect(savedValues.length).toBe(1);
    expect(savedValues[0].webhook_enabled).toBe(true);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Cancel handler
  // ──────────────────────────────────────────────────────────────────────────

  it('resets form on cancel', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;

    // Simulate user changing the URL
    comp.formState.update((s: WebhookConfig) => ({...s, webhook_url: 'https://changed.example.com'}));
    expect(comp.formState().webhook_url).toBe('https://changed.example.com');

    // Cancel should reset to original config
    comp.onCancel();
    expect(comp.formState().webhook_url).toBe(BEARER_CONFIG.webhook_url);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Password masking
  // ──────────────────────────────────────────────────────────────────────────

  it('masks password fields (type=password on bearer token input)', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    // syn-input elements with type="password"
    const passwordInputs = compiled.querySelectorAll('syn-input[type="password"]');
    expect(passwordInputs.length).toBeGreaterThan(0);
  });

  it('masks password fields (type=password on basic auth password input)', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BASIC_CONFIG);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    const passwordInputs = compiled.querySelectorAll('syn-input[type="password"]');
    expect(passwordInputs.length).toBeGreaterThan(0);
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Auth type switching clears stale credentials
  // ──────────────────────────────────────────────────────────────────────────

  it('clears stale credentials when switching auth type', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;

    // Simulate switching from bearer to basic
    comp.onAuthTypeChange(new CustomEvent('syn-change', {detail: {value: 'basic'}}));

    expect(comp.formState().webhook_auth_token).toBeNull();
    expect(comp.formState().webhook_auth_type).toBe('basic');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Custom headers
  // ──────────────────────────────────────────────────────────────────────────

  it('renders existing custom headers from config', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', {
      ...DEFAULT_WEBHOOK_CONFIG,
      webhook_enabled: true,
      webhook_url: 'https://example.com',
      webhook_custom_headers: {'X-Source': 'lidar'},
    });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    // "Custom Headers" section label appears as text in the template
    expect(compiled.textContent).toContain('Custom Headers');
    // And the header row should have an input for the key
    const inputs = compiled.querySelectorAll('syn-input[placeholder="Header name"]');
    expect(inputs.length).toBe(1);
  });

  it('isDirty is false when formState matches config', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.isDirty()).toBe(false);
  });

  it('isDirty is true when formState differs from config', () => {
    const fixture = TestBed.createComponent(WebhookConfigComponent);
    fixture.componentRef.setInput('config', BEARER_CONFIG);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    comp.formState.update((s: WebhookConfig) => ({...s, webhook_url: 'https://new.example.com'}));

    expect(comp.isDirty()).toBe(true);
  });
});
