import { Injectable } from '@angular/core';
import { SynAlert } from '@synergy-design-system/components';
import { MsddService } from './msdd.service';
import { Subject } from 'rxjs';
import { debounceTime, share, tap } from 'rxjs/operators';
import { UntilDestroy, untilDestroyed } from '@ngneat/until-destroy';

export interface ToastConfig {
  message: string;
  variant: SynAlert['variant'];
  duration?: number;
  icon?: string;
}

@UntilDestroy()
@Injectable({
  providedIn: 'root',
})
export class ToastService {
  private toastQueue$ = new Subject<ToastConfig>();
  private destroy$ = new Subject<void>();

  // Shared observable for toast processing
  private processedToasts$ = this.toastQueue$.pipe(
    untilDestroyed(this),
    debounceTime(100),
    tap((config) => this.displayToast(config)),
    share({
      connector: () => new Subject(),
      resetOnRefCountZero: true,
    }),
  );

  constructor() {
    // Subscribe to processed toasts
    this.processedToasts$.subscribe();
  }

  // Convenience methods remain the same
  public primary(message: string, duration: number = 3000): void {
    this.enqueueToast({ message, variant: 'primary', duration });
  }

  public success(message: string, duration: number = 3000): void {
    this.enqueueToast({
      message,
      variant: 'success',
      icon: 'check_circle',
      duration,
    });
  }

  public neutral(message: string, duration: number = 3000): void {
    this.enqueueToast({ message, variant: 'neutral', duration });
  }

  public warning(message: string, duration: number = 3000): void {
    this.enqueueToast({
      message,
      variant: 'warning',
      icon: 'warning',
      duration,
    });
  }

  public danger(message: string, duration: number = 3000): void {
    this.enqueueToast({
      message,
      variant: 'danger',
      icon: 'error',
      duration,
    });
  }

  private displayToast(config: ToastConfig): void {
    const { message, variant, duration = 3000 } = config;

    // Use service method or fallback to a default icon
    const icon = config.icon || MsddService.getToastIcon(variant);

    const alert = this.createToastAlert(message, variant, icon);

    document.body.append(alert);
    alert.toast();
  }

  private createToastAlert(message: string, variant: SynAlert['variant'], icon: string): any {
    return Object.assign(document.createElement('syn-alert'), {
      variant,
      closable: true,
      duration: 3000,
      innerHTML: `
        <syn-icon src="${MsddService.getToastIcon(icon)}" slot="icon"></syn-icon>
        <strong>Notification</strong>
        <br />
        ${this.escapeHtml(message)}
      `,
    });
  }

  // Enqueue a toast notification
  private enqueueToast(config: ToastConfig): void {
    this.toastQueue$.next(config);
  }

  // Escape HTML to prevent XSS
  private escapeHtml(html: string): string {
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
  }
}
