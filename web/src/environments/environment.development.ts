export const environment = {
  production: false,
  apiUrl: 'http://lenovo:8005/api/v1',
  staticUrl: 'http://lenovo:8005',
  wsUrl: (topic: string) => `ws://lenovo:8005/api/v1/ws/${topic}`,
  mockShapes: false,
};
