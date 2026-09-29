# Cloudflare 1027 与多设备探测频率

检查日期：2026-09-30，Asia/Shanghai。Cloudflare Analytics 的日期按 UTC；
2026-09-29 UTC 对应北京时间 9 月 29 日 08:00 至 9 月 30 日 08:00。
首次统计截至 2026-09-29 23:05:28 UTC（北京时间 9 月 30 日 07:05:28），
当天尚未结束。以下请求数为 Analytics 返回值，可能包含自适应采样估计，
并非逐条计费日志。

## 结论与证据

主要额度消耗来自本项目的 EdgeTunnel 代理，不是配置订阅拉取。

| UTC 日期 | surge-edgetunnel 请求 | surge-config-service 请求 |
|---|---:|---:|
| 2026-09-28 | 103,959 | 24 |
| 2026-09-29，截至上述时间 | 105,870 | 16 |

同账户还有其他 Workers，共享额度，因此不能将账户所有消耗都归到本项目。
初次统计中 9 月 29 日账户请求合计 119,159。
稍后按 EdgeTunnel 状态复查时，包含 exceededResources、loadShed 和
scriptThrewException。状态统计随时间继续增长；clientDisconnected
本身不能作为代理故障的证据。

通过现有 us1 HTTPS 代理分别读取 edge.fallback.page 根路径和
config.fallback.page/health，两者均返回包含 error code: 1027 的响应。
查询 Cloudflare 管理 API 也需要避开当时失败的默认 CF 代理路径。
以上只读检查未修改 Worker、账号套餐、DNS 或代理出口规则。

Cloudflare 官方说明：Workers Free 账户每日 100,000 次请求，UTC 午夜
（北京时间 08:00）重置；超额时返回 1027。不能把 Cloudflare CDN 免费流量、
Workers 请求额度、Workers KV 额度和管理 API 速率限制混为一谈。

## 已实施的本地调整

- surge.conf 的 7 个 url-test 组和 shadowrocket.conf 的 8 个 url-test 组：
  interval 从 300 改为 7200 秒，即 2 小时。
- Surge 的上述 7 个组设置 evaluate-before-use=false。已有过期结果时先用
  当前选择并后台刷新；首次没有结果时先使用组内第一个节点，不等待探测成功。
- Surge 托管配置保留 interval=86400 strict=false：下载失败可以继续使用
  已下载的本地配置。这里的配置缓存与节点探测结果是两回事。
- AI 固定出口、地区节点池、所有分流规则和 FINAL,DIRECT 未变。
- 本机活动配置只修改相同的探测参数，备份保存在忽略目录
  build/surge.before-20260930-probe-interval.conf（含凭据，不得公开）。

Surge 的 interval 是结果有效期，不是固定定时任务或严格重试上限。闲置组
不一定探测；网络变化、节点故障和手动测速仍可能触发提前探测。
不保证所有探测失败后永久保留上次成功节点，也不保证 Shadowrocket 的
失败处理与 Surge 相同。1027 导致代理本身不可用时，缓存不能恢复连接。

以 10 台设备持续使用 CF 组、每轮 7 个独立节点或按三个组的 14 个成员项
分别计算，常规探测连接估算从每天 20,160–40,320 降至 840–1,680，减少
约 95.8%。这是容量估算，不是实测的探测流量分解；未计客户端去重、休眠、
网络变化、故障重试或实际业务代理连接。仅降低探测不能保证不再耗尽额度。

## 验证与发布状态

- 两份配置各 81 个路由案例通过。
- check-rules.sh 通过；默认网络路径曾超时，改用现有 us1 HTTPS 代理完成检查。
- 两份配置渲染成功；凭据只保存在忽略的 build/ 目录。
- 本机 Surge reload 成功，并在随后 effective profile 中确认 7 个组均为
  interval=7200、evaluate-before-use=false；活动配置的代理定义和规则与备份相同。
- 用户已授权提交并发布。配置服务按需读取 GitHub main，模板推送无需重新
  部署 Worker。其他设备需要成功更新订阅后才会获取本次调整。
- 本地验收时 1027 尚未恢复。降低频率不会撤销当天已消耗的额度；发布后也需要
  各设备更新，并观察下一完整 UTC 日的 Worker 请求量。

## 官方资料

- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/#daily-requests)
- [Cloudflare Workers GraphQL metrics](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/)
- [Surge 自动测试组](https://manual.nssurge.com/policy-groups/url-test.html)
- [Surge 测试与异常重测](https://kb.nssurge.com/surge-knowledge-base/technotes/testing-group)
- [Surge 托管配置 strict 参数](https://manual.nssurge.com/profile/managed-profile.html)
