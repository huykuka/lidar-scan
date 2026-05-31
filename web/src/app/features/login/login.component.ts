import {Component, inject, signal} from '@angular/core';
import {Router} from '@angular/router';
import {FormsModule} from '@angular/forms';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {AuthService} from '@core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, SynergyComponentsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  protected username = signal('');
  protected password = signal('');
  protected isLoading = signal(false);
  protected errorMessage = signal<string | null>(null);

  protected async onSubmit(event: Event) {
    event.preventDefault();
    const user = this.username().trim();
    const pass = this.password();

    if (!user || !pass) {
      this.errorMessage.set('Please enter both username and password.');
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    try {
      await this.auth.login(user, pass);
      this.router.navigate(['/']);
    } catch {
      this.errorMessage.set('Invalid username or password.');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected onUsernameInput(event: Event) {
    this.username.set((event.target as HTMLInputElement).value);
  }

  protected onPasswordInput(event: Event) {
    this.password.set((event.target as HTMLInputElement).value);
  }
}
