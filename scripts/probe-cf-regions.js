// Run with: surge-cli script evaluate scripts/probe-cf-regions.js generic 120
// Read-only: forces each existing CF leaf without changing any group selection.
// Country results are observations, not a guarantee of future exit locations.
const policies = [
  "CF Edge Direct SG", "CF Edge CT 01 US", "CF Edge CT 02 US",
  "CF Edge CU 01 US", "CF Edge CU 02 US", "CF Edge CM 01 SG",
  "CF Edge CM 02 SG"
];
const targets = [
  {name: "ipinfo", url: "https://ipinfo.io/json"},
  {name: "cloudflare", url: "https://www.cloudflare.com/cdn-cgi/trace"}
];
const pending = [];
policies.forEach((policy) => targets.forEach((target) => pending.push({policy, target})));
const results = [];
function next() {
  const job = pending.shift();
  if (!job) {
    console.log(JSON.stringify({measured_at: new Date().toISOString(), results}));
    $done();
    return;
  }
  const started = Date.now();
  $httpClient.get({url: job.target.url, policy: job.policy, timeout: 7}, (error, response, body) => {
    const result = {policy: job.policy, target: job.target.name,
      status: response && response.status, error: error || null,
      elapsed_ms: Date.now() - started, ip: null, country: null};
    if (!error && response && response.status === 200) {
      try {
        if (job.target.name === "ipinfo") {
          const info = JSON.parse(body);
          result.ip = info.ip || null;
          result.country = info.country || null;
          result.city = info.city || null;
        } else {
          const trace = {};
          String(body || "").split("\n").forEach((line) => {
            const index = line.indexOf("=");
            if (index > 0) trace[line.slice(0, index)] = line.slice(index + 1);
          });
          result.ip = trace.ip || null;
          result.country = trace.loc || null;
          result.target_colo = trace.colo || null;
        }
      } catch (_) { result.error = "Unrecognized response"; }
    }
    results.push(result);
    console.log(JSON.stringify(result));
    next();
  });
}
next();
