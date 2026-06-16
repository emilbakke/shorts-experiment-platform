export function isPrivateLanHost(hostname: string): boolean {
  if (!hostname) return false;
  if (hostname === "localhost" || hostname === "127.0.0.1") return true;
  if (/^10(?:\.\d{1,3}){3}$/.test(hostname)) return true;
  if (/^192\.168(?:\.\d{1,3}){2}$/.test(hostname)) return true;
  const match = hostname.match(/^172\.(\d{1,3})(?:\.\d{1,3}){2}$/);
  if (!match) return false;
  const secondOctet = Number(match[1]);
  return Number.isInteger(secondOctet) && secondOctet >= 16 && secondOctet <= 31;
}

export function isClientSideDevHost(): boolean {
  if (typeof window === "undefined") return false;
  return isPrivateLanHost(window.location.hostname);
}

export function isRequestHostAllowedForDev(requestHost: string): boolean {
  const hostname = requestHost.trim().split(":")[0] ?? "";
  return isPrivateLanHost(hostname);
}
