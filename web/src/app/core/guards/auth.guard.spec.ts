import {TestBed} from '@angular/core/testing';
import {Router} from '@angular/router';
import {provideRouter} from '@angular/router';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting, HttpTestingController} from '@angular/common/http/testing';
import {serviceGuard} from './auth.guard';
import {AuthService, UserRole} from '@core/services/auth.service';
import {environment} from '@env/environment';

describe('serviceGuard', () => {
  let authService: AuthService;
  let router: Router;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  async function loginAs(role: UserRole) {
    const p = authService.login('test', 'test');
    const req = httpTesting.expectOne(`${environment.apiUrl}/auth/login`);
    req.flush({
      access_token: 'tok',
      token_type: 'bearer',
      user: {id: '1', username: 'test', role},
    });
    await p;
  }

  function runGuard(): boolean | ReturnType<Router['createUrlTree']> {
    return TestBed.runInInjectionContext(() =>
      serviceGuard({} as any, {} as any),
    ) as boolean | ReturnType<Router['createUrlTree']>;
  }

  it('should redirect to "/" when not authenticated', () => {
    const result = runGuard();
    expect(result).not.toBe(true);
    expect(result.toString()).toBe('/');
  });

  it('should redirect to "/" for user role', async () => {
    await loginAs('user');
    const result = runGuard();
    expect(result).not.toBe(true);
    expect(result.toString()).toBe('/');
  });

  it('should redirect to "/" for admin role', async () => {
    await loginAs('admin');
    const result = runGuard();
    expect(result).not.toBe(true);
    expect(result.toString()).toBe('/');
  });

  it('should allow access for service role', async () => {
    await loginAs('service');
    const result = runGuard();
    expect(result).toBe(true);
  });
});
