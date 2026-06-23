import { Injectable, signal } from '@angular/core';


export type DialogSeverity = 'danger' | 'warning' | 'success' | 'primary';

export interface DialogConfig {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmIcon?: string;
  confirmSeverity?: DialogSeverity;
  variant?: 'danger' | 'neutral';
  onConfirm?: () => void;
  onCancel?: () => void;
}
@Injectable({
  providedIn: 'root',
})
export class DialogService {
  private dialogState = signal<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    confirmIcon: string;
    confirmSeverity: DialogSeverity;
  } | null>(null);

  readonly isOpen = signal(false);
  readonly title = signal('');
  readonly message = signal('');
  readonly confirmLabel = signal('');
  readonly confirmIcon = signal('check');
  readonly confirmSeverity = signal<DialogSeverity>('danger');

  private onConfirmCallback: (() => void) | undefined;
  private onCancelCallback: (() => void) | undefined;

  confirm(config: DialogConfig | string): Promise<boolean> {
    const finalConfig: DialogConfig =
      typeof config === 'string' ? { message: config } : config;

    const {
      title = 'Confirm',
      message,
      confirmLabel = 'Confirm',
      cancelLabel,
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

    void cancelLabel;

    this.title.set(title);
    this.message.set(message);
    this.confirmLabel.set(confirmLabel);
    this.confirmIcon.set(confirmIcon);
    this.confirmSeverity.set(severity);
    this.onConfirmCallback = onConfirm;
    this.onCancelCallback = onCancel;

    return new Promise<boolean>((resolve) => {
      this.isOpen.set(true);

      // Override callbacks to include resolution
      const originalConfirm = this.onConfirmCallback;
      const originalCancel = this.onCancelCallback;

      this.onConfirmCallback = () => {
        originalConfirm?.();
        this.accept();
        resolve(true);
      };

      this.onCancelCallback = () => {
        originalCancel?.();
        this.cancel();
        resolve(false);
      };
    });
  }

  accept(): void {
    this.onConfirmCallback?.();
    this.close();
  }

  cancel(): void {
    this.onCancelCallback?.();
    this.close();
  }

  private close(): void {
    this.isOpen.set(false);
    this.title.set('');
    this.message.set('');
    this.confirmLabel.set('');
    this.confirmIcon.set('check');
    this.confirmSeverity.set('danger');
  }
}
