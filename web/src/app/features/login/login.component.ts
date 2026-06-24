import {Component, inject, signal, ChangeDetectionStrategy} from '@angular/core';
import {Router} from '@angular/router';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {AuthService} from '@core/services/auth.service';
import {ToastService} from '@core/services';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, SynergyComponentsModule, SynergyFormsModule],
  templateUrl: './login.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  private toast = inject(ToastService);

  protected readonly form = new FormGroup({
    username: new FormControl('', [Validators.required]),
    password: new FormControl('', [Validators.required]),
  });

  protected isLoading = signal(false);

  protected async onSubmit() {
    const { username, password } = this.form.getRawValue();
    this.isLoading.set(true);

    try {
      await this.auth.login(username!, password!);
      this.router.navigate(['/']);
    } catch {
      this.toast.danger('Invalid username or password.');
    } finally {
      this.isLoading.set(false);
    }
  }
}
