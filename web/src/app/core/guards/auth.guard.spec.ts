import {TestBed} from '@angular/core/testing';
import {provideRouter, Router} from '@angular/router';
import {serviceGuard} from './auth.guard';
import {AuthService} from '@core/services/auth.service';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';

describe('serviceGuard', () => {
  let auth: AuthService;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    auth = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should redirect to / when not authenticated', () => {
    const result = TestBed.runInInjectionContext(() => serviceGuard({} as any, {} as any));
    expect(result).toEqual(router.createUrlTree(['/']));
  });

  it('should redirect to / when logged in as user', () => {
    localStorage.setItem('auth_user', JSON.stringify({id: '1', username: 'user', role: 'user'}));
    localStorage.setItem('auth_token', 'tok');
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const result = TestBed.runInInjectionContext(() => serviceGuard({} as any, {} as any));
    expect(result).toEqual(TestBed.inject(Router).createUrlTree(['/']));
  });

  it('should redirect to / when logged in as admin', () => {
    localStorage.setItem('auth_user', JSON.stringify({id: '1', username: 'admin', role: 'admin'}));
    localStorage.setItem('auth_token', 'tok');
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const result = TestBed.runInInjectionContext(() => serviceGuard({} as any, {} as any));
    expect(result).toEqual(TestBed.inject(Router).createUrlTree(['/']));
  });

  it('should allow access when logged in as service', () => {
    localStorage.setItem('auth_user', JSON.stringify({id: '1', username: 'service', role: 'service'}));
    localStorage.setItem('auth_token', 'tok');
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const result = TestBed.runInInjectionContext(() => serviceGuard({} as any, {} as any));
    expect(result).toBe(true);
  });
});
