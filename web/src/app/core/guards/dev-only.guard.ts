import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { environment } from '../../../environments/environment';

export const DevOnlyGuard: CanActivateFn = (route, state) => {
  const router = inject(Router);

  if (!environment.production) {
    return true;
  }

  console.warn('[DevOnly] Performance dashboard is not available in production builds.');
  return router.createUrlTree(['/']);
};