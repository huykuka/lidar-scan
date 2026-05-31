import {HttpInterceptorFn} from '@angular/common/http';
import {inject} from '@angular/core';
import {catchError, throwError} from 'rxjs';
import {AuthService} from '@core/services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);

  const token = auth.getToken();
  const isAuthEndpoint = req.url.includes('/auth/login');

  if (token && !isAuthEndpoint) {
    req = req.clone({
      setHeaders: {Authorization: `Bearer ${token}`},
    });
  }

  return next(req).pipe(
    catchError((err) => {
      if (err.status === 401 && !isAuthEndpoint) {
        auth.logout();
      }
      return throwError(() => err);
    }),
  );
};
