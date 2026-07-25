import {
  ApplicationConfig,
  ErrorHandler,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners, isDevMode,
} from '@angular/core';
import {provideNgtRenderer} from 'angular-three/dom';
import {PreloadAllModules, provideRouter, withPreloading} from '@angular/router';
import {provideHttpClient, withInterceptors, withXhr} from '@angular/common/http';

import {routes} from './app.routes';
import {authInterceptor} from '@core/interceptors/auth.interceptor';
import {httpToastInterceptor} from '@core/interceptors/http-toast.interceptor';
import {GlobalErrorHandler} from '@core/errors/global-error.handler';
import {AppInitService} from '@core/services/app-init.service';
import { provideServiceWorker } from '@angular/service-worker';

export const appConfig: ApplicationConfig = {
  providers: [
    provideNgtRenderer(),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withPreloading(PreloadAllModules)),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor, httpToastInterceptor])),
    { provide: ErrorHandler, useClass: GlobalErrorHandler },
    provideAppInitializer(() => inject(AppInitService).init()), provideServiceWorker('ngsw-worker.js', {
            enabled: !isDevMode(),
            registrationStrategy: 'registerWhenStable:30000'
          }),
  ],
};
