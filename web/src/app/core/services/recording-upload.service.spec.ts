import {TestBed} from '@angular/core/testing';
import {HttpEventType} from '@angular/common/http';
import {Subject} from 'rxjs';
import {describe, expect, it, vi} from 'vitest';
import {RecordingApiService} from './api/recording-api.service';
import {RecordingStoreService} from './stores/recording-store.service';
import {RecordingUploadService} from './recording-upload.service';

describe('RecordingUploadService', () => {
  function setup() {
    const streams: Subject<unknown>[] = [];
    const api = {
      uploadRecordingWithProgress: vi.fn(() => {
        const s = new Subject<unknown>();
        streams.push(s);
        return s.asObservable();
      }),
    };
    TestBed.configureTestingModule({
      providers: [
        {provide: RecordingApiService, useValue: api},
        {provide: RecordingStoreService, useValue: {refresh: vi.fn()}},
      ],
    });
    return {svc: TestBed.inject(RecordingUploadService), streams};
  }

  it('updates each file progress from upload events and starts at most 2', () => {
    const {svc, streams} = setup();
    svc.enqueue([new File(['a'], 'a.mcap'), new File(['b'], 'b.mcap'), new File(['c'], 'c.mcap')]);
    expect(streams.length).toBe(2);
    streams[0].next({type: HttpEventType.UploadProgress, loaded: 25, total: 100});
    streams[1].next({type: HttpEventType.UploadProgress, loaded: 60, total: 100});
    expect(svc.items().map((i) => [i.status, i.progress])).toEqual([
      ['uploading', 25],
      ['uploading', 60],
      ['queued', 0],
    ]);
  });

  it('cancel aborts the transfer and starts the next queued file', () => {
    const {svc, streams} = setup();
    svc.enqueue([new File(['a'], 'a.mcap'), new File(['b'], 'b.mcap'), new File(['c'], 'c.mcap')]);
    svc.cancel(1);
    expect(streams[0].observed).toBe(false);
    expect(streams.length).toBe(3);
    expect(svc.items().map((i) => i.name)).toEqual(['b.mcap', 'c.mcap']);
  });
});
