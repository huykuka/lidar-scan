export const environment = {
  production: false,
  apiUrl: 'http://192.168.100.17:8005/api/v1',
  staticUrl: 'http://192.168.100.17:8005',
  wsUrl: (topic: string) => `ws://192.168.100.17:8005/api/v1/ws/${topic}`,
  mockShapes: false,
};
