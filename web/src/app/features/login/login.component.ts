import {Component, inject, signal} from '@angular/core';
import {Router} from '@angular/router';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {AuthService} from '@core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  protected readonly form = new FormGroup({
    username: new FormControl('', [Validators.required]),
    password: new FormControl('', [Validators.required]),
  });

  protected isLoading = signal(false);
  protected errorMessage = signal<string | null>(null);

  protected async onSubmit() {
    if (this.form.invalid) {
      this.errorMessage.set('Please enter both username and password.');
      return;
    }

    const {username, password} = this.form.getRawValue();
    this.isLoading.set(true);
    this.errorMessage.set(null);

    try {
      await this.auth.login(username!, password!);
      this.router.navigate(['/']);
    } catch {
      this.errorMessage.set('Invalid username or password.');
    } finally {
      this.isLoading.set(false);
    }
  }
}
