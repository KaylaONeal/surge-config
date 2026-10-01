// Read-only policy-specific probes. No credentials or protected URLs are logged.
const policies = ["CF Edge Auto", "CF Edge CT 01 US", "CF Edge CU 01 US", "CF Edge CM 01 SG", "AI"];
const results = [];
function next() {
  const policy = policies.shift();
  if (!policy) {
    console.log(JSON.stringify({results}));
    $done();
    return;
  }
  const started = Date.now();
  $httpClient.get({url: "https://www.cloudflare.com/cdn-cgi/trace", policy, timeout: 10}, (error, response, body) => {
    const trace = {};
    String(body || "").split("\n").forEach((line) => {
      const index = line.indexOf("=");
      if (index > 0) trace[line.slice(0, index)] = line.slice(index + 1);
    });
    const result = {policy, status: response && response.status, error: error || null,
      ip: trace.ip || null, country: trace.loc || null, colo: trace.colo || null,
      elapsed_ms: Date.now() - started};
    results.push(result);
    console.log(JSON.stringify(result));
    next();
  });
}
next();
