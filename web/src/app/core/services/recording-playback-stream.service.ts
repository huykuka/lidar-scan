import {Injectable} from '@angular/core';
import {Observable, Subject} from 'rxjs';
import {environment} from '@env/environment';
import {parseLidrFrame, LidrFrame, LidrFrameError} from './lidr-parser';

export interface ReadyEvent {type: 'ready'; frameCount: number; startFrameIndex: number; generation: number}
export interface SeekedEvent {type: 'seeked'; frameIndex: number; generation: number}
export interface EofEvent {type: 'eof'; frameIndex: number; generation: number}
export interface PausedEvent {type: 'paused'; frameIndex: number; generation: number}
export interface StreamError {type: 'error'; code: string; message: string}
export type RecordingPlaybackEvent = ReadyEvent | SeekedEvent | PausedEvent | LidrFrame | EofEvent | StreamError;

@Injectable({providedIn: 'root'})
export class RecordingPlaybackStreamService {
  private socket: WebSocket | null = null;
  private readonly eventsSubject = new Subject<RecordingPlaybackEvent>();
  readonly events: Observable<RecordingPlaybackEvent> = this.eventsSubject.asObservable();

  connect(recordingId: string): void {
    this.disconnect();
    const wsApiUrl = environment.apiUrl.replace(/^http/, 'ws');
    const url = `${wsApiUrl}/recordings/${encodeURIComponent(recordingId)}/stream`;
    const socket = this.socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    socket.onmessage = (event) => this.handleMessage(event.data);
    socket.onerror = () => this.eventsSubject.next({type: 'error', code: 'connection_error', message: 'Recording stream connection failed'});
    socket.onclose = () => { if (this.socket === socket) this.socket = null; };
  }

  start(frameIndex?: number): void { this.send({type: 'start', ...(frameIndex === undefined ? {} : {frameIndex})}); }
  seek(frameIndex: number): void { this.send({type: 'seek', frameIndex}); }
  pause(): void { this.send({type: 'pause'}); }

  disconnect(): void {
    if (!this.socket) return;
    this.socket.onclose = null;
    this.socket.close();
    this.socket = null;
  }

  private send(command: {type: 'start' | 'seek'; frameIndex?: number} | {type: 'pause'}): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(command));
  }

  private handleMessage(data: string | ArrayBuffer): void {
    if (data instanceof ArrayBuffer) {
      const parsed = parseLidrFrame(data);
      this.eventsSubject.next(parsed as LidrFrame | LidrFrameError);
      if (parsed.type === 'error') this.disconnect();
      return;
    }
    try {
      const message = JSON.parse(data) as RecordingPlaybackEvent;
      this.eventsSubject.next(message);
    } catch {
      this.eventsSubject.next({type: 'error', code: 'invalid_message', message: 'Invalid stream message'});
    }
  }
}
