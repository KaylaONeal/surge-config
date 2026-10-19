// Read-only target-specific probes; does not select a group or access accounts.
// Run: surge-cli script evaluate scripts/probe-polymarket-hk.js generic 120
const policies = ["CF HKG 01", "CF HKG 02", "CF HKG Auto"];
const targets = [
  {name: "geoblock", url: "https://polymarket.com/api/geoblock"},
  {name: "clob-time", url: "https://clob.polymarket.com/time"},
  {name: "perps-time", url: "https://api.perpetuals.polymarket.com/v1/info/time"}
];
const jobs = [];
policies.forEach((policy) => targets.forEach((target) => jobs.push({policy, target})));
targets.forEach((target) => jobs.push({policy: null, target}));
function next() {
  const job = jobs.shift();
  if (!job) { $done(); return; }
  const started = Date.now();
  const options = {url: job.target.url, timeout: 8};
  if (job.policy) options.policy = job.policy;
  $httpClient.get(options, (error, response, body) => {
    const result = {policy: job.policy || "RULES", target: job.target.name,
      status: response && response.status, error: error || null,
      elapsed_ms: Date.now() - started};
    if (!error && response && response.status === 200 && job.target.name === "geoblock") {
      try {
        const data = JSON.parse(body);
        result.ip = data.ip || null;
        result.country = data.country || null;
        result.region = data.region || null;
        result.blocked = data.blocked;
      } catch (_) { result.error = "Unrecognized geoblock response"; }
    }
    console.log(JSON.stringify(result));
    next();
  });
}
next();
