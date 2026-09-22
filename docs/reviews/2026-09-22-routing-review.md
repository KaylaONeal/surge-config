# Surge 分流与软件下载评估

检查日期：2026-09-22，Asia/Shanghai；出口与下载测量集中于 13:14–13:18。范围：本机 Surge、仓库模板、公开安装源与社区维护者文档。本文记录变更前的诊断及候选方案。后续用户批准前三项，明确不采用第 4 项；实际实施保留 FINAL,DIRECT，见 [部署记录](2026-09-22-deployment.md)。

## 结论

现有配置保护国内/公司网络及固定 AI 出口的设计有价值，但“未知流量直连”和“开发者下载集中使用 CF Edge”的取向，与频繁使用新海外 AI 软件的需求不匹配。优先优化下载路径和兜底逻辑，无须整套替换配置。

## 已核实的状态

- 本机 Surge 5.7.6，系统 HTTP/HTTPS 代理为 127.0.0.1:6152。实际请求有规则命中和 Enhanced Mode 接管记录。
- 两份模板均通过 `python3 scripts/check-routing.py`，各 59 项路由检查。这只能证明现有约束一致，不证明覆盖新域名或下载快。
- 客户端记忆的 `AI` 选择是 `US HTTPS 01`，绕过 `US Only` 的自动选择；模板默认值并不代表当前选择。
- Cloudflare trace 的逐策略探测：AI、US HY2 02、US HY2 01 均观察到美国出口 35.212.192.172；CF Edge Auto 此时为美国 104.28.165.56；KR HTTPS 01 为韩国 104.28.211.29。仅代表本次测量。
- `muse.ai`、`auth.muse.ai` 的正常请求均命中 `FINAL → DIRECT`。显式指定 US HY2 02 后，首页返回 307 到 auth.muse.ai，携带原始跳转参数继续请求返回 302 到 www.facebook.com。未登录账号，也未验证登录后的功能。
- 新版 Claude Code 安装脚本实际使用 `https://downloads.claude.ai/claude-code-releases`。官方文档称 2.1.116 之前的版本使用 storage.googleapis.com，不能只按旧教程补 Google Storage。
- 当前 Codex 独立安装脚本首选 `https://releases.openai.com/codex`，也包含 GitHub 后备下载路径。npm 安装源为 registry.npmjs.org。
- 日志确认 releases.openai.com、downloads.claude.ai 使用 `AI → US HTTPS 01`；registry.npmjs.org 使用 `CF Edge Auto → CF Edge CT 01 US`。

## 官方文件片段下载

方法：Surge `$httpClient` 按策略发起 HTTPS Range GET，串行比较，包含连接建立时间。成功样本均返回 HTTP 206，核对实际字节数及 Content-Range。未执行安装脚本或安装软件。第一轮每项 2 MiB，第二轮三个文件各取另一个 8 MiB 片段，反转两个策略的测试顺序。总计成功接收 70 MiB；另有一次超时。

第一轮，单位 MiB/s：

| 文件 | AI / 当前 HTTPS | US HY2 02 | CF Edge Auto |
|---|---:|---:|---:|
| Codex Mac 安装包 | 0.422 | 0.724 | 0.498 |
| Codex 原生 CLI | 0.494 | 2.030 | 18 秒超时 |
| Claude Code | 0.874 | 3.643 | 0.245 |
| Codex npm 原生包 | 0.733 | 2.361 | 0.728 |

第二轮，单位 MiB/s：

| 文件 | AI / 当前 HTTPS | US HY2 02 |
|---|---:|---:|
| Codex Mac 安装包 | 2.042 | 2.596 |
| Codex 原生 CLI | 2.850 | 5.662 |
| Claude Code | 2.928 | 5.161 |

样本为 Codex CLI 0.155.1、Claude Code 2.1.278，以及 Homebrew cask 元数据指向的 Codex Mac 26.623.141536 安装包。Mac 包仅用来比较同一官方 CDN 文件的线路，并非断言其为用户当前要下载的最新应用版本。

两轮均显示 US HY2 02 更快；HTTPS 本身波动较大。片段测试不能外推为整个安装包的稳定速度，也不能覆盖其他时段、设备或网络。

## 建议的实施顺序

1. **补齐 Muse 的显式规则。** 将 `DOMAIN-SUFFIX,muse.ai,AI` 放到宽泛规则之前，同时维护 ai-extra.list。它涵盖 auth 等子域名。沿真实登录流程检查 Facebook 及资源域名的出口一致性；只补后缀不等于登录验收完成。Meta 公告称产品目前在美国推出，宜沿用现有固定美国 AI 出口。

2. **让 AI 使用同出口的更优传输。** 当前三个 US Only 成员实测出口相同。可将 US Only 改为基础 Smart 组，并把客户端 AI 的已记忆选择改回 US Only；或先固定实测较快的 US HY2 02。只改组定义不能覆盖客户端仍固定 HTTPS 的选择。Smart 优化连接质量及故障切换，并非带宽测速器。当前 Mac 5.7.6 支持基础 Smart；共享到 iOS 前需检查版本与授权，Shadowrocket 保留其支持的组类型。

3. **增加独立 Download 策略。** 首选本次更快的 US HY2 02，提供同出口替代传输及人工切换。针对 persistent.oaistatic.com、releases.openai.com、downloads.claude.ai、registry.npmjs.org、release-assets.githubusercontent.com 等实际下载域名单独分流，规则放在宽泛 AI / Google / GitHub 集合之前。旧版 Claude 的 storage.googleapis.com 单独评估，避免将整个 googleapis.com、amazonaws.com、cloudfront.net 当作下载域名处理。

4. **更换未知流量的兜底取向。** 对频繁尝试新海外工具的使用习惯，建议“公司/内网和已知国内服务直连，其余兜底代理”，兜底默认可选稳定美国出口。规则末尾采用国内 IP 直连判定及 `FINAL,<兜底策略>,dns-failed`，同时保留靠前的国内域名直连快路径。代价是未收录的国内域名可能走代理、代理流量增加。此项改变现有明确的 FINAL,DIRECT 约束，需要同步更新 README 与路由检查，不能只改 FINAL 或删除检查。公司系统 DNS、AI 固定出口、交易所专用出口继续保留。

5. **采用社区的分层方式，控制规则来源数量。** 可以保留当前 Blackmatrix 国内/全球主规则库，吸收 Sukka 的 AI、CDN、域名规则与 IP 规则分层方式；需要替换广域规则时逐项比较覆盖，避免叠加多套完整库。个人规则处理新服务的收录时差。新 AI 的地域要求仍需专门规则，通用代理兜底只解决漏代理的一部分问题。

实际改动后的验收应包括：受影响的首匹配检查、`bash scripts/check-rules.sh`、渲染与客户端加载、已发布版本核对，以及真实安装下载和 Muse 登录流程。这些变更后的检查及实际采用范围另记于部署记录。

## 来源

- [Surge Smart 官方手册](https://manual.nssurge.com/policy-groups/smart.html)：基础支持 Mac 5.7.0 / iOS 5.11.0 起，按实际连接质量选路；Smart 成员不能嵌套组。
- [Surge Smart 官方说明](https://kb.nssurge.com/surge-knowledge-base/guidelines/smart-group)：客户端版本、iOS 授权及敏感网站独立分流。
- [Surge DNS 官方说明](https://kb.nssurge.com/surge-knowledge-base/technotes/dns)：域名规则优先，代理兜底使用 dns-failed。
- [SukkaW/Surge](https://github.com/SukkaW/Surge)：AI、CDN、国内与国际规则分层；域名规则先于需要解析的 IP 规则。
- [Loyalsoldier/surge-rules](https://github.com/Loyalsoldier/surge-rules)：白名单模式以 FINAL,PROXY,dns-failed 兜底；黑名单模式以直连兜底。
- [Blackmatrix Surge 规则目录](https://github.com/blackmatrix7/ios_rule_script/blob/master/rule/Surge/README.md)：现有服务分类规则来源。
- [Claude Code 网络官方文档](https://code.claude.com/docs/en/network-config)：现行与历史安装下载域名、npm 源。
- [OpenAI 官方 Codex CLI 文档](https://developers.openai.com/codex/cli)：当前安装脚本入口；具体下载目标另读取该脚本核对，未执行脚本。
- [Meta Muse 发布公告](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)：2026-09-08 发布及美国推出范围。

原始测试脚本和脱敏结果临时保存在 `/tmp/surge-audit-20260922/`。报告不包含凭据、受保护配置 URL 或登录跳转查询参数。
