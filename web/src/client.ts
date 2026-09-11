let token = "";
export function setToken(value: string) {
  token = value;
}
export async function request(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  headers.set("X-Paper-Lab-Token", token);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, { ...options, headers });
  if (!response.ok) {
    let message = "请求失败，请重试。";
    try {
      const value = await response.json();
      message =
        typeof value.detail === "string"
          ? value.detail
          : "输入不符合要求，请检查。";
    } catch {}
    throw new Error(message);
  }
  return response;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  return (
    await request(path, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  ).json();
}
