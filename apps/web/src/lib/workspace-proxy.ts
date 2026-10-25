/** Ownership is derived only after the backend verifies this ALB signature. */
export function backendHeaders(incoming: Headers, apiKey = ""): Headers {
  const headers = new Headers();
  if (apiKey) headers.set("x-api-key", apiKey);
  const identity = incoming.get("x-amzn-oidc-data");
  if (identity) headers.set("x-amzn-oidc-data", identity);
  return headers;
}
