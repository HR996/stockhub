/**
 * Frontend-side user directory (P2-05 stub).
 *
 * Later this should be fetched from the backend once the auth endpoint exists.
 * For now the list is hard-coded to match the backend's `PRECONFIGURED_USERS`
 * default (`admin`).
 */

export interface UserOption {
  username: string;
  label: string;
}

export function listPreconfiguredUsers(): UserOption[] {
  return [
    { username: "admin", label: "admin (管理员)" },
  ];
}
