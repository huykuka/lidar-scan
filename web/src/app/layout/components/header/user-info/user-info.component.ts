import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { SynergyComponentsModule, SynergyFormsModule } from '@synergy-design-system/angular';
import { AuthService } from '@core/services/auth.service';

@Component({
  selector: 'app-user-info',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './user-info.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './user-info.component.css',
})
export class UserInfoComponent {
  protected readonly auth = inject(AuthService);

  protected readonly loginForm = new FormGroup({
    username: new FormControl('', [Validators.required]),
    password: new FormControl('', [Validators.required]),
  });
  protected readonly dropdownOpen = signal(false);
  protected readonly loginLoading = signal(false);
  protected readonly loginError = signal<string | null>(null);

  protected async onLogin(): Promise<void> {
    if (this.loginForm.invalid) return;

    const { username, password } = this.loginForm.getRawValue();
    this.loginLoading.set(true);
    this.loginError.set(null);

    try {
      await this.auth.login(username!, password!);
      this.loginForm.reset();
      this.dropdownOpen.set(false);
    } catch {
    } finally {
      this.loginLoading.set(false);
    }
  }

  protected onDropdownShow(): void {
    this.dropdownOpen.set(true);
  }

  protected onDropdownHide(): void {
    this.dropdownOpen.set(false);
    this.loginError.set(null);
  }

  protected onLogout(): void {
    this.auth.logout();
  }
}
