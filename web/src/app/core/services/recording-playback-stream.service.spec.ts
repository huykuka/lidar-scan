import {RecordingPlaybackStreamService} from './recording-playback-stream.service';

describe('RecordingPlaybackStreamService', () => {
  let service: RecordingPlaybackStreamService;
  let socket: any;

  beforeEach(() => {
    socket = {readyState: 1, send: vi.fn(), close: vi.fn(), set binaryType(_: string) {}};
    vi.stubGlobal('WebSocket', class MockWebSocket {
      static OPEN = 1;
      readyState = 1;
      send = socket.send;
      close = socket.close;
      set binaryType(value: string) { socket.binaryType = value; }
      set onmessage(value: any) { socket.onmessage = value; }
      set onerror(value: any) { socket.onerror = value; }
      set onclose(value: any) { socket.onclose = value; }
      constructor(url: string) { (WebSocket as any).url = url; }
    });
    service = new RecordingPlaybackStreamService();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('connects endpoint and sends start/seek commands', () => {
    const events: any[] = [];
    service.events.subscribe((event) => events.push(event));
    service.connect('rec 1');
    expect((WebSocket as any).url).toContain('/api/v1/recordings/rec%201/stream');
    service.start(0); service.seek(1250);
    expect(socket.send).toHaveBeenNthCalledWith(1, '{"type":"start","frameIndex":0}');
    expect(socket.send).toHaveBeenNthCalledWith(2, '{"type":"seek","frameIndex":1250}');
    socket.onmessage({data: JSON.stringify({type: 'ready', frameCount: 3, startFrameIndex: 0, generation: 0})});
    expect(events[0].type).toBe('ready');
  });

  it('parses binary errors and closes socket', () => {
    service.connect('rec');
    socket.onmessage({data: new ArrayBuffer(0)});
    expect(socket.close).toHaveBeenCalled();
  });
});
