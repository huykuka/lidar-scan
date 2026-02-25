import { ErrorHandler, Injectable, inject } from '@angular/core';
import { ToastService } from '../services/toast.service';
import { SystemStatusService } from '../services/system-status.service';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private toast = inject(ToastService);
  private systemStatus = inject(SystemStatusService);

  handleError(error: unknown): void {
    const message = this.normalize(error) || 'Unexpected error.';

    // Ignore ResizeObserver loop errors as they are non-critical browser warnings
    // often triggered during transitions or layout shifts and don't affect app state.
    if (message.includes('ResizeObserver loop')) {
      return;
    }

    // Always log for debugging
    // eslint-disable-next-line no-console
    console.error(error);

    this.toast.danger(message);
    this.systemStatus.report('error', message);
  }

  private normalize(err: unknown): string | null {
    if (!err) return null;
    if (typeof err === 'string') return err;
    if (err instanceof Error) return err.message;
    if (typeof err === 'object') {
      const anyErr: any = err;
      const msg = anyErr?.message || anyErr?.detail || anyErr?.error;
      return typeof msg === 'string' ? msg : null;
    }
    return null;
  }
}
