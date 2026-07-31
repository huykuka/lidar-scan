import {HttpErrorResponse} from '@angular/common/http';
import {ErrorHandler, inject, Injectable} from '@angular/core';
import {ToastService} from '@core/services';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  private toast = inject(ToastService);

  handleError(error: unknown): void {
    const message = this.normalize(error) || 'Unexpected error.';
    if (!(error instanceof HttpErrorResponse)) {
      return;
    }

    // Ignore ResizeObserver loop errors as they are non-critical browser warnings
    // often triggered during transitions or layout shifts and don't affect app state.
    if (message.includes('ResizeObserver loop')) {
      return;
    }

    // Always log for debugging
    // eslint-disable-next-line no-console
    console.error(error);

    // toast.danger() internally calls systemStatus.report('error', ...) — no need to duplicate.
    this.toast.danger(this.friendlyHttpMessage(error, message));
  }

  /** Map raw HttpErrorResponse text into a user-friendly message. */
  private friendlyHttpMessage(err: HttpErrorResponse, fallback: string): string {
    const fromBody = this.normalize(err.error);
    if (fromBody) return fromBody;

    switch (true) {
      case err.status === 0:
        return 'Cannot reach backend. Check connection.';
      case err.status >= 500:
        return 'Backend error. Please retry.';
      case err.status === 404:
        return 'Endpoint not found.';
      case err.status === 401:
        return 'Not authorized.';
      case err.status === 403:
        return 'Access denied.';
      default:
        return fallback;
    }
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
