const TEMPLATE_BASE = "https://raw.githubusercontent.com/KaylaONeal/surge-config/main";

const SECRET_NAMES = [
  "HTTPS_USERNAME",
  "HTTPS_PASSWORD",
  "TUIC_USERNAME",
  "TUIC_PASSWORD",
  "TUIC_UUID",
  "HY2_USERNAME",
  "HY2_PASSWORD",
  "EDGETUNNEL_UUID",
];

function secureEqual(actual, expected) {
  const a = new TextEncoder().encode(actual || "");
  const b = new TextEncoder().encode(expected || "");
  let mismatch = a.length ^ b.length;
  const length = Math.max(a.length, b.length);

  for (let index = 0; index < length; index += 1) {
    mismatch |= (a[index % Math.max(a.length, 1)] || 0) ^
      (b[index % Math.max(b.length, 1)] || 0);
  }

  return mismatch === 0;
}

function textResponse(body, status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      ...extraHeaders,
    },
  });
}

async function loadTemplate(name, env) {
  const headers = {};
  if (env.GITHUB_TOKEN) headers.authorization = `Bearer ${env.GITHUB_TOKEN}`;

  const response = await fetch(`${TEMPLATE_BASE}/${name}`, {
    headers,
    cf: { cacheTtl: 60, cacheEverything: true },
  });

  if (!response.ok) {
    throw new Error(`template fetch failed: ${name} (${response.status})`);
  }

  return response.text();
}

function render(template, values) {
  return template.replace(/__([A-Z0-9_]+)__/g, (_, name) => {
    if (!(name in values) || !values[name]) {
      throw new Error(`missing render value: ${name}`);
    }
    return values[name];
  });
}

function installerPage(baseUrl) {
  const surgeUrl = `${baseUrl}/surge.conf`;
  const shadowrocketUrl = `${baseUrl}/shadowrocket.conf`;
  const surgeImport = `surge:///install-config?url=${encodeURIComponent(surgeUrl)}`;
  const shadowrocketImport = `shadowrocket://config/add/${shadowrocketUrl}`;

  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>代理配置安装</title>
<style>
body{font:16px system-ui;max-width:560px;margin:48px auto;padding:0 20px;color:#172033}
h1{font-size:26px}a{display:block;margin:16px 0;padding:16px;border-radius:12px;background:#1769e0;color:#fff;text-align:center;text-decoration:none}
p{line-height:1.6;color:#536075}.secondary{background:#303846}
</style>
<h1>一键安装代理配置</h1>
<p>Surge 会每天从此受保护地址更新。Shadowrocket 将此地址添加为远程配置。</p>
<a href="${surgeImport}">导入 Surge</a>
<a class="secondary" href="${shadowrocketImport}">导入 Shadowrocket</a>
</html>`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return textResponse("ok\n");

    const parts = url.pathname.split("/").filter(Boolean);
    const suppliedToken = parts.shift() || "";
    if (!secureEqual(suppliedToken, env.ACCESS_TOKEN)) {
      return textResponse("not found\n", 404);
    }

    const baseUrl = `${url.origin}/${encodeURIComponent(suppliedToken)}`;
    const resource = parts.join("/");

    if (!resource) {
      return new Response(installerPage(baseUrl), {
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "private, no-store",
          "x-content-type-options": "nosniff",
          "referrer-policy": "no-referrer",
        },
      });
    }

    if (resource !== "surge.conf" && resource !== "shadowrocket.conf") {
      return textResponse("not found\n", 404);
    }

    try {
      const values = Object.fromEntries(SECRET_NAMES.map((name) => [name, env[name]]));
      values.SURGE_MANAGED_URL = `${baseUrl}/surge.conf`;
      const rendered = render(await loadTemplate(resource, env), values);
      return textResponse(rendered, 200, {
        "content-disposition": `inline; filename="${resource}"`,
      });
    } catch (error) {
      console.error(error);
      return textResponse("configuration temporarily unavailable\n", 503);
    }
  },
};

