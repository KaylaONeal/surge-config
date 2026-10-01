// Compare the new ingress through the existing US policy and the local line.
const ingress = "https://edge-bcd7d61c.pages.dev/";
const policies = ["AI", "DIRECT"];
function next() {
  const policy = policies.shift();
  if (!policy) { $done(); return; }
  const started = Date.now();
  $httpClient.get({url: ingress, policy, timeout: 8}, (error, response, body) => {
    console.log(JSON.stringify({policy, status: response && response.status,
      error: error || null, elapsed_ms: Date.now() - started,
      public_body_preview: String(body || "").slice(0, 160).replace(/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/gi, "[REDACTED]")}));
    next();
  });
}
next();
