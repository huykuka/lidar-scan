import {inject} from '@angular/core';
import {CanActivateFn, Router} from '@angular/router';
import {AuthService} from '@core/services/auth.service';

export const serviceGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isService()) {
    return router.createUrlTree(['/']);
  }
  return true;
};
