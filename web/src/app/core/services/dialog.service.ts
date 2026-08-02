import {Injectable, signal} from '@angular/core';


export type DialogSeverity = 'danger' | 'warning' | 'success' | 'primary';

export interface DialogCheckbox {
  key: string;
  label: string;
  checked?: boolean;
}

export interface DialogConfig {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmIcon?: string;
  confirmSeverity?: DialogSeverity;
  variant?: 'danger' | 'neutral';
  checkboxes?: DialogCheckbox[];
  onConfirm?: () => void;
  onCancel?: () => void;
}

interface PendingDialogRequest {
  config: DialogConfig;
  resolve: (result: boolean) => void;
}

@Injectable({
  providedIn: 'root',
})
export class DialogService {
  readonly isOpen = signal(false);
  readonly title = signal('');
  readonly message = signal('');
  readonly confirmLabel = signal('');
  readonly cancelLabel = signal('Cancel');
  readonly confirmIcon = signal('check');
  readonly confirmSeverity = signal<DialogSeverity>('danger');
  readonly checkboxes = signal<DialogCheckbox[]>([]);
  /** Mutable map of checkbox states; keyed by DialogCheckbox.key. */
  readonly checkboxValues = signal<Record<string, boolean>>({});

  private onConfirmCallback: (() => void) | undefined;
  private onCancelCallback: (() => void) | undefined;
  private resolver: ((result: boolean) => void) | undefined;
  private pendingQueue: PendingDialogRequest[] = [];

  confirm(config: DialogConfig | string): Promise<boolean> {
    const finalConfig: DialogConfig = typeof config === 'string' ? { message: config } : config;

    return new Promise<boolean>((resolve) => {
      const request: PendingDialogRequest = { config: finalConfig, resolve };

      if (this.isOpen()) {
        this.pendingQueue.push(request);
        return;
      }

      this.openDialog(request);
    });
  }

  toggleCheckbox(key: string): void {
    this.checkboxValues.update((v) => ({ ...v, [key]: !v[key] }));
  }

  accept(): void {
    this.onConfirmCallback?.();
    this.resolver?.(true);
    this.close();
    this.openNextIfAny();
  }

  cancel(): void {
    this.onCancelCallback?.();
    this.resolver?.(false);
    this.close();
    this.openNextIfAny();
  }

  private openDialog(request: PendingDialogRequest): void {
    const finalConfig = request.config;

    const {
      title = 'Confirm',
      message,
      confirmLabel = 'Confirm',
      cancelLabel = 'Cancel',
      confirmIcon = 'check',
      confirmSeverity,
      variant,
      onConfirm,
      onCancel,
    } = finalConfig;

    // Map variant to confirmSeverity for backward compatibility
    let severity: DialogSeverity = 'danger';
    if (confirmSeverity) {
      severity = confirmSeverity;
    } else if (variant === 'neutral') {
      severity = 'primary';
    }

    this.title.set(title);
    this.message.set(message);
    this.confirmLabel.set(confirmLabel);
    this.cancelLabel.set(cancelLabel);
    this.confirmIcon.set(confirmIcon);
    this.confirmSeverity.set(severity);
    // Reset checkbox state here so values from the previous dialog don't bleed in
    const boxes = finalConfig.checkboxes ?? [];
    this.checkboxes.set(boxes);
    this.checkboxValues.set(Object.fromEntries(boxes.map((c) => [c.key, c.checked ?? false])));
    this.onConfirmCallback = onConfirm;
    this.onCancelCallback = onCancel;
    this.resolver = request.resolve;
    this.isOpen.set(true);
  }

  private close(): void {
    this.isOpen.set(false);
    this.title.set('');
    this.message.set('');
    this.confirmLabel.set('');
    this.cancelLabel.set('Cancel');
    this.confirmIcon.set('check');
    this.confirmSeverity.set('danger');
    // checkboxes/checkboxValues intentionally NOT cleared here — caller reads them after await
    this.onConfirmCallback = undefined;
    this.onCancelCallback = undefined;
    this.resolver = undefined;
  }

  private openNextIfAny(): void {
    const next = this.pendingQueue.shift();
    if (!next) return;
    this.openDialog(next);
  }
}
