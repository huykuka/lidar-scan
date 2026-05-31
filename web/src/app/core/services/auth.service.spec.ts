import {TestBed} from '@angular/core/testing';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {provideHttpClient} from '@angular/common/http';
import {AuthService, UserRole} from './auth.service';
import {environment} from '@env/environment';

describe('AuthService', () => {
  let service: AuthService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should start unauthenticated', () => {
    expect(service.isAuthenticated()).toBe(false);
    expect(service.user()).toBeNull();
    expect(service.getToken()).toBeNull();
  });

  describe('login', () => {
    it('should set user and token on successful login', async () => {
      const loginPromise = service.login('admin', 'admin');

      const req = httpTesting.expectOne(`${environment.apiUrl}/auth/login`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({username: 'admin', password: 'admin'});

      req.flush({
        access_token: 'test-jwt-token',
        token_type: 'bearer',
        user: {id: '1', username: 'admin', role: 'admin'},
      });

      await loginPromise;

      expect(service.isAuthenticated()).toBe(true);
      expect(service.user()!.username).toBe('admin');
      expect(service.user()!.role).toBe('admin');
      expect(service.getToken()).toBe('test-jwt-token');
    });

    it('should persist token and user to localStorage', async () => {
      const loginPromise = service.login('admin', 'admin');

      const req = httpTesting.expectOne(`${environment.apiUrl}/auth/login`);
      req.flush({
        access_token: 'stored-token',
        token_type: 'bearer',
        user: {id: '1', username: 'admin', role: 'admin'},
      });

      await loginPromise;

      expect(localStorage.getItem('auth_token')).toBe('stored-token');
      expect(JSON.parse(localStorage.getItem('auth_user')!).username).toBe('admin');
    });
  });

  describe('logout', () => {
    it('should clear user and token', async () => {
      const loginPromise = service.login('service', 'service');
      const req = httpTesting.expectOne(`${environment.apiUrl}/auth/login`);
      req.flush({
        access_token: 'tok',
        token_type: 'bearer',
        user: {id: '1', username: 'service', role: 'service'},
      });
      await loginPromise;

      service.logout();

      expect(service.isAuthenticated()).toBe(false);
      expect(service.user()).toBeNull();
      expect(service.getToken()).toBeNull();
      expect(localStorage.getItem('auth_token')).toBeNull();
      expect(localStorage.getItem('auth_user')).toBeNull();
    });
  });

  describe('role computed signals', () => {
    async function loginAs(role: UserRole) {
      const p = service.login('test', 'test');
      const req = httpTesting.expectOne(`${environment.apiUrl}/auth/login`);
      req.flush({
        access_token: 'tok',
        token_type: 'bearer',
        user: {id: '1', username: 'test', role},
      });
      await p;
    }

    it('isAdmin is false for user role', async () => {
      await loginAs('user');
      expect(service.isAdmin()).toBe(false);
    });

    it('isAdmin is true for admin role', async () => {
      await loginAs('admin');
      expect(service.isAdmin()).toBe(true);
    });

    it('isAdmin is true for service role (service >= admin)', async () => {
      await loginAs('service');
      expect(service.isAdmin()).toBe(true);
    });

    it('isService is false for user role', async () => {
      await loginAs('user');
      expect(service.isService()).toBe(false);
    });

    it('isService is false for admin role', async () => {
      await loginAs('admin');
      expect(service.isService()).toBe(false);
    });

    it('isService is true for service role', async () => {
      await loginAs('service');
      expect(service.isService()).toBe(true);
    });

    it('canEdit equals isAdmin', async () => {
      expect(service.canEdit()).toBe(false);

      await loginAs('user');
      expect(service.canEdit()).toBe(false);

      service.logout();
      await loginAs('admin');
      expect(service.canEdit()).toBe(true);

      service.logout();
      await loginAs('service');
      expect(service.canEdit()).toBe(true);
    });

    it('isAdmin is false when not authenticated', () => {
      expect(service.isAdmin()).toBe(false);
    });

    it('isService is false when not authenticated', () => {
      expect(service.isService()).toBe(false);
    });
  });
});
