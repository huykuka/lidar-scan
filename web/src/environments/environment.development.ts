export const environment = {
  production: false,
  apiUrl: 'http://localhost:8004/api/v1',
  wsUrl: (topic: string) => `ws://localhost:8004/api/v1/ws/${topic}`,
  mockStatus: false, // Set to true to use mock status data with cycling states
};
