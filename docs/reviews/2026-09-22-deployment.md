# 2026-09-22 下载与 Muse 分流变更

用户批准补齐 Muse、独立下载策略和同出口 AI 自动选路，明确保留 `FINAL,DIRECT`。国内/公司系统 DNS 和交易所规则保持原策略。

- Surge 的 `US Only` 改为基础 Smart，成员仍为 US HY2 02、US HY2 01、US HTTPS 01；Shadowrocket 保持 url-test。
- 本机已将记忆选择切到 `AI → US Only`，`Download → US HY2 02`。
- Download 的 7 个准确下载主机优先于宽泛 AI/GitHub 规则，所有可选路径都保持 us1 出口。
- `muse.ai` 及公开跳转链的准确主机 www.facebook.com、www.instagram.com、auth.meta.com 使用 AI。其他访问这三个 Meta 主机的请求也会使用固定美国出口。
- 完整变更前测量及未采用的兜底建议保存在 [评估报告](2026-09-22-routing-review.md)。

## 本地验收

- 两份配置各通过 81 项路由检查，检查包含下载规则优先级、Smart 的叶子节点成员、固定出口成员范围，以及未知流量直连。
- `bash scripts/check-rules.sh` 全部通过：36 个规则 URL 检查，无失败；渲染通过，输出保存在忽略的 build/，权限 0600。
- 本机原配置和策略选择已备份至 `~/.config/surge-config/backups/20260922-133523/`，新配置重载成功。
- 13:36 的逐策略 Cloudflare trace：AI 与 Download 均为 35.212.192.172 / US。
- Muse 普通规则请求完成 muse.ai → auth.muse.ai → Facebook → Instagram → auth.meta.com → auth.muse.ai → muse.ai，最终 HTTP 200，标题为 Muse — Your Personal AI Agent。未登录或验证账号功能。
- 普通 HTTP 代理请求下载官方文件片段，每项 4 MiB，均为 HTTP 206；日志确认四项都使用 `Download → US HY2 02`：

| 下载 | MiB/s |
|---|---:|
| Codex Mac | 3.719 |
| Codex CLI | 4.632 |
| Claude Code | 6.099 |
| Codex npm | 3.244 |

片段速率只代表此次网络条件，不能当作整包持续速度。不同轮次片段大小和连接状态不同，不能直接用本表计算变更前后的倍数。

## 当前发布验收状态

- 配置提交 `e8dc6f7` 已推送 main，[GitHub CI 35691848785](https://github.com/KaylaONeal/surge-config/actions/runs/35691848785) 成功；本机配置及策略选择已生效。
- GitHub raw 的两份模板均与提交内容一致。
- 线上 Surge 与 Shadowrocket 均返回 HTTP 200，下载内容逐字节匹配本地渲染配置，确认新规则、策略组及凭据渲染均已发布。
- Surge 托管内容曾在 push 后延迟同步；后续复验已更新，无需重部署 Worker 或恢复 Cloudflare 登录。

## 发布方式与兼容性

配置服务直接读取 GitHub main 并按需渲染，模板发布不需要修改或重新部署 Worker。验收比较线上两份鉴权配置与已推送模板，而非只检查健康端点。Surge 脚本读取其自身托管配置 URL 时返回 127.0.0.1:6154 拒绝连接；独立 HTTPS 代理下载两份配置均正常，因此线上模板一致性通过独立下载链路核验。

Surge 基础 Smart 要求 Mac 5.7.0+ 或 iOS 5.11.0+ 且已解锁；本机 Mac 5.7.6 已实测。此次没有连接手机验证其运行版本、授权或已记忆的 AI 选择。Shadowrocket 模板保持兼容的 url-test。
