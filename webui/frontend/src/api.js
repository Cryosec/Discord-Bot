// src/api.js
// fetch wrapper for the /api routes: a 401 means the session is gone (expired,
// or the moderator role was removed), so the app logs out.

let unauthorizedHandler = null;

// AuthProvider registers its logout here (pass null to unregister)
export const setUnauthorizedHandler = (handler) => {
  unauthorizedHandler = handler;
};

export class UnauthorizedError extends Error {
  constructor() {
    super('Session expired (401). Please log in again.');
    this.name = 'UnauthorizedError';
  }
}

export const apiFetch = async (url, options = {}) => {
  const response = await fetch(url, { credentials: 'include', ...options });
  if (response.status === 401) {
    if (unauthorizedHandler) {
      unauthorizedHandler();
    }
    throw new UnauthorizedError();
  }
  return response;
};
