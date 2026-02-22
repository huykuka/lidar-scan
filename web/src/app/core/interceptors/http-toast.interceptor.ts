import {
  HttpContextToken,
  HttpErrorResponse,
  HttpInterceptorFn,
  HttpResponse,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, tap, throwError } from 'rxjs';
import { ToastService } from '../services/toast.service';
import { SystemStatusService } from '../services/system-status.service';

const SILENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export const TOAST_ON_ERROR = new HttpContextToken<boolean>(() => false);
export const TOAST_ON_SUCCESS = new HttpContextToken<boolean>(() => false);

function normalizeMessage(value: unknown): string | null {
  if (!value) return null;

  if (typeof value === 'string') return value;

  if (typeof value === 'object') {
    const obj: any = value;
    const msg = obj?.message || obj?.detail || obj?.error;
    if (typeof msg === 'string') return msg;
  }

  return null;
}

function isBackendStatusError(body: any): boolean {
  return !!body && typeof body === 'object' && body.status === 'error';
}

export const httpToastInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  const systemStatus = inject(SystemStatusService);

  const method = (req.method || '').toUpperCase();
  const silent = SILENT_METHODS.has(method);
  const toastOnError = req.context.get(TOAST_ON_ERROR);
  const toastOnSuccess = req.context.get(TOAST_ON_SUCCESS);

  return next(req).pipe(
    tap((event) => {
      if (!(event instanceof HttpResponse)) return;

      // Backends sometimes respond 200 with {status:"error"}; treat as user-visible error.
      const body: any = event.body;
      if (isBackendStatusError(body)) {
        const msg = normalizeMessage(body) || 'Request failed.';
        toast.danger(msg);
        systemStatus.report('error', msg);
        return;
      }

      // Non-GET requests: show success if backend provides a message.
      const msg = normalizeMessage(body);
      if (!silent || toastOnSuccess) {
        if (msg) toast.success(msg);
        else if (body?.status === 'success') toast.success('Done.');
      }
    }),
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse) {
        const status = err.status;
        const body: any = err.error;
        const msgFromBody = normalizeMessage(body);

        let message = msgFromBody;
        if (!message) {
          if (status === 0) message = 'Cannot reach backend. Check connection.';
          else if (status >= 500) message = 'Backend error. Please retry.';
          else if (status === 404) message = 'Endpoint not found.';
          else if (status === 401) message = 'Not authorized.';
          else if (status === 403) message = 'Access denied.';
          else message = err.message || 'Request failed.';
        }

        if (!silent || toastOnError) toast.danger(message);
        systemStatus.report('error', message);
      } else {
        const message = normalizeMessage(err) || 'Unexpected error.';
        if (!silent || toastOnError) toast.danger(message);
        systemStatus.report('error', message);
      }

      return throwError(() => err);
    }),
  );
};
