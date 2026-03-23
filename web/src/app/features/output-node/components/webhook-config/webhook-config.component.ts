import {Component, effect, inject, input, OnInit, output, signal, computed} from '@angular/core';
import {ReactiveFormsModule} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {WebhookConfig, DEFAULT_WEBHOOK_CONFIG} from '@core/models/output-node.model';
import {OutputNodeApiService} from '@features/output-node/services/output-node-api.service';
import {ToastService} from '@core/services/toast.service';

/** Custom header row in the form state */
interface HeaderRow {
  key: string;
  value: string;
}

/**
 * Validate webhook URL: returns an error string or null.
 */
export function validateWebhookUrl(url: string, enabled: boolean): string | null {
  if (!enabled) return null;
  if (!url || url.trim() === '') return 'URL is required when webhook is enabled';
  try {
    const parsed = new URL(url.trim());
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return 'URL must use http:// or https://';
    }
  } catch {
    return 'Invalid URL format';
  }
  return null;
}

/**
 * Warn if URL is plain HTTP (not HTTPS).
 */
export function warnWebhookUrl(url: string, enabled: boolean): string | null {
  if (!enabled || !url) return null;
  try {
    const parsed = new URL(url.trim());
    if (parsed.protocol === 'http:') {
      return 'Consider using HTTPS for security';
    }
  } catch {
    // ignore — validation error will catch this
  }
  return null;
}

/**
 * Dumb form component: webhook configuration for an Output Node.
 * Rendered inside the Settings drawer when an output_node is selected.
 */
@Component({
  selector: 'app-webhook-config',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './webhook-config.component.html',
})
export class WebhookConfigComponent implements OnInit {
  config = input<WebhookConfig>(DEFAULT_WEBHOOK_CONFIG);
  nodeId = input<string>('');
  webhookSaved = output<WebhookConfig>();

  private outputNodeApi = inject(OutputNodeApiService);
  private toast = inject(ToastService);

  protected formState = signal<WebhookConfig>({...DEFAULT_WEBHOOK_CONFIG});
  protected customHeaders = signal<HeaderRow[]>([]);
  protected isSaving = signal(false);

  protected urlValidationError = computed(() =>
    validateWebhookUrl(this.formState().webhook_url, this.formState().webhook_enabled),
  );

  protected urlWarning = computed(() =>
    warnWebhookUrl(this.formState().webhook_url, this.formState().webhook_enabled),
  );

  protected isDirty = computed(
    () => JSON.stringify(this.formState()) !== JSON.stringify(this.config()),
  );

  constructor() {
    // Sync form state when config input changes
    effect(() => {
      const cfg = this.config();
      this.formState.set({...cfg});
      const headers = cfg.webhook_custom_headers ?? {};
      this.customHeaders.set(
        Object.entries(headers).map(([key, value]) => ({key, value})),
      );
    });
  }

  ngOnInit(): void {}

  // ---- Enable toggle ----
  protected onToggleEnabled(event: Event): void {
    const checked = (event as CustomEvent).detail?.checked ?? (event.target as HTMLInputElement).checked;
    this.formState.update(s => ({...s, webhook_enabled: checked}));
  }

  // ---- URL input ----
  protected onUrlChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_url: value}));
  }

  // ---- Auth type change ----
  protected onAuthTypeChange(event: Event): void {
    const value = (event as CustomEvent).detail?.value ?? (event.target as HTMLSelectElement).value;
    this.formState.update(s => ({
      ...s,
      webhook_auth_type: value as WebhookConfig['webhook_auth_type'],
      // Clear stale credentials when switching auth type
      webhook_auth_token: null,
      webhook_auth_username: null,
      webhook_auth_password: null,
      webhook_auth_key_name: 'X-API-Key',
      webhook_auth_key_value: null,
    }));
  }

  // ---- Credential inputs ----
  protected onTokenChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_auth_token: value || null}));
  }

  protected onUsernameChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_auth_username: value || null}));
  }

  protected onPasswordChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_auth_password: value || null}));
  }

  protected onKeyNameChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_auth_key_name: value || null}));
  }

  protected onKeyValueChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.formState.update(s => ({...s, webhook_auth_key_value: value || null}));
  }

  // ---- Custom headers ----
  protected addHeader(): void {
    this.customHeaders.update(rows => [...rows, {key: '', value: ''}]);
  }

  protected removeHeader(index: number): void {
    this.customHeaders.update(rows => rows.filter((_, i) => i !== index));
    this.syncHeadersToFormState();
  }

  protected onHeaderKeyChange(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.customHeaders.update(rows =>
      rows.map((row, i) => (i === index ? {...row, key: value} : row)),
    );
    this.syncHeadersToFormState();
  }

  protected onHeaderValueChange(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.customHeaders.update(rows =>
      rows.map((row, i) => (i === index ? {...row, value} : row)),
    );
    this.syncHeadersToFormState();
  }

  private syncHeadersToFormState(): void {
    const headers: Record<string, string> = {};
    for (const row of this.customHeaders()) {
      if (row.key.trim()) {
        headers[row.key.trim()] = row.value;
      }
    }
    this.formState.update(s => ({...s, webhook_custom_headers: headers}));
  }

  // ---- Save / Cancel ----
  async onSave(): Promise<void> {
    if (this.urlValidationError()) return;

    this.isSaving.set(true);
    try {
      await this.outputNodeApi.updateWebhookConfig(this.nodeId(), this.formState());
      this.toast.success('Webhook configuration saved.');
      this.webhookSaved.emit(this.formState());
    } catch {
      this.toast.danger('Failed to save webhook configuration.');
    } finally {
      this.isSaving.set(false);
    }
  }

  onCancel(): void {
    const cfg = this.config();
    this.formState.set({...cfg});
    const headers = cfg.webhook_custom_headers ?? {};
    this.customHeaders.set(
      Object.entries(headers).map(([key, value]) => ({key, value})),
    );
  }
}
