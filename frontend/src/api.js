// Клиент API. Токен сессии передаётся в заголовке, а не в URL.
const API_URL = (
  import.meta.env.VITE_API_URL || ''
).replace(/\/$/, '');

const BASE = `${API_URL}/api/v1`;

async function request(path, { method = 'GET', token, body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['X-Session-Token'] = token;
  const response = await fetch(BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Сервис временно недоступен. Попробуйте ещё раз.');
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  createSession: () => request('/sessions', { method: 'POST', body: { channel: 'web' } }),
  maxLogin: (token) => request('/integrations/max/auth', { method: 'POST', body: { token } }),
  getSession: (id, token) => request(`/sessions/${id}`, { token }),
  answer: (id, token, payload) => request(`/sessions/${id}/answers`, { method: 'POST', token, body: payload }),
  back: (id, token) => request(`/sessions/${id}/back`, { method: 'POST', token }),
  remove: (id, token) => request(`/sessions/${id}`, { method: 'DELETE', token }),
};
