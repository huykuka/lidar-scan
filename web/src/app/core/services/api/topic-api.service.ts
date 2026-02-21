import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { firstValueFrom, map } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class TopicApiService {
  private http = inject(HttpClient);

  async getTopics(): Promise<string[]> {
    try {
      const data$ = this.http
        .get<{ topics: string[] }>(`${environment.apiUrl}/topics`)
        .pipe(map((res) => res.topics || []));
      return await firstValueFrom(data$);
    } catch (error) {
      console.error('Error fetching topics:', error);
      return [];
    }
  }
}
