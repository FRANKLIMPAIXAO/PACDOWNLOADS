// HTTP client wrapper que injeta automaticamente o header Authorization.
// Usa fetch nativo para manter o stack enxuto (sem axios).

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
/** URL absoluta da API — útil para fetch direto (ex: download de blob). */
export const API_BASE_URL = API_URL;
const TOKEN_STORAGE_KEY = "pac_xml_token";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

type ApiOptions = RequestInit & { skipAuth?: boolean };

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { skipAuth, headers, body, ...rest } = options;

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  const finalHeaders: Record<string, string> = {
    ...(headers as Record<string, string> | undefined),
  };

  // Para FormData, NAO settar Content-Type — o browser inclui o boundary do
  // multipart automaticamente. Para JSON (default), forcar application/json.
  if (!isFormData && !finalHeaders["Content-Type"] && body !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
  }

  if (!skipAuth) {
    const token = getStoredToken();
    if (token) {
      finalHeaders["Authorization"] = `Bearer ${token}`;
    }
  }

  const url = `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
  let response: Response;
  try {
    response = await fetch(url, { ...rest, headers: finalHeaders, body });
  } catch (err) {
    throw new ApiError(0, null, `Falha de rede: ${(err as Error).message}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    const message =
      typeof detail === "string"
        ? detail
        : `Erro ${response.status} em ${path}`;
    throw new ApiError(response.status, detail, message);
  }

  return payload as T;
}
