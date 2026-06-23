import { Injectable, signal, computed, inject } from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {catchError, of} from 'rxjs';
import {environment} from '@env/environment';

export type UserRole = 'user' | 'admin' | 'service';

export interface UserInfo {
  id: string;
  username: string;
  role: UserRole;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

@Injectable({providedIn: 'root'})
export class AuthService {
  private http = inject(HttpClient);

  private readonly currentUser = signal<UserInfo | null>(this.loadUserFromStorage());
  private readonly token = signal<string | null>(this.loadTokenFromStorage());

  private static readonly ROLE_LEVELS: Record<UserRole, number> = {user: 0, admin: 1, service: 2};

  readonly user = this.currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this.currentUser() !== null);
  readonly isAdmin = computed(() => {
    const role = this.currentUser()?.role;
    return role !== undefined && AuthService.ROLE_LEVELS[role] >= AuthService.ROLE_LEVELS['admin'];
  });
  readonly isService = computed(() => this.currentUser()?.role === 'service');
  readonly canEdit = this.isAdmin;

  getToken(): string | null {
    return this.token();
  }

  /** Called at app boot. Validates the stored token against the backend.
   *  Clears auth state if no token is present or the server rejects it. */
  async verifyToken(): Promise<void> {
    if (!this.token()) return;
    const user = await firstValueFrom(
      this.http.get<UserInfo>(`${environment.apiUrl}/auth/me`).pipe(
        catchError(() => {
          this.logout();
          return of(null);
        }),
      ),
    );
    if (user) {
      this.currentUser.set(user);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  }

  async login(username: string, password: string): Promise<UserInfo> {
    const res = await firstValueFrom(
      this.http.post<LoginResponse>(`${environment.apiUrl}/auth/login`, {username, password}),
    );
    this.token.set(res.access_token);
    this.currentUser.set(res.user);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    return res.user;
  }

  logout(): void {
    this.token.set(null);
    this.currentUser.set(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  private loadTokenFromStorage(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  private loadUserFromStorage(): UserInfo | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
}
