# 直播源测速交接包

在本机网络（与电视盒同宽带）实测每条直播线路的真实下载速率，按 Mbps 重排，
产出可直接给 FongMi/TV 订阅的 txt。

## 1. 为什么需要本机测速

云端（GitHub Actions）跑在海外，它测出的"最快"对国内移动/电信没有参考价值。
实测证据：同一批 166 条线路，云端排序把央视的源全排在前面，但国内移动家宽逐条复测——

| 源 | 云端判定 | 国内移动实测 |
|---|---|---|
| 黑龙江移动 OTT（`ottrrs.hl.chinamobile.com`） | 能连通，排最前 | **0 Mbps**（跨省受限） |
| 美国 IP 中转（`74.91.26.218` 等） | 延迟最低 | **0 Mbps**（绕美国） |
| 咪咕 CDN（`hlsztemgsplive.miguvideo.com`，移动自有） | 连不上，从未入选 | **2.75~16.98 Mbps** |
| 河北广电（`event.pull.hebtv.com`） | 一般 | **55~59 Mbps** |

结论：排序必须在本机做。这个包就是干这个的。

## 2. 环境要求

- Python **3.8+**，**不需要任何第三方库**（纯标准库）。
- 测速强制直连，**不走系统代理**（走代理测的是代理速度，结果无意义）。
- 测速期间不要同时看视频/下载，否则带宽被抢，结果偏低。

## 3. 快速开始

```bash
# 方式 A：用自带源池快照（3256 条，最快，不联网）
python speedtest.py

# 方式 B：现场从 subscribe.txt 抓源建池（源池更新时用，需要能访问 GitHub）
python speedtest.py --subscribe

# 方式 C：测一个现成的 txt/m3u 文件
python speedtest.py --src samples/user_result.txt
```

Windows 双击 `run.bat`，Linux/macOS 用 `./run.sh`，参数可追加在后面。

第一次建议先跑 `python speedtest.py --limit 40` 验证环境（约 30 秒），
确认输出的速率不是全 0，再跑全量。

## 4. 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--pool` | `pool.txt` | 源池快照路径 |
| `--subscribe` | 关 | 现场从 `subscribe.txt` 抓源建池 |
| `--src` | — | 直接测指定 txt/m3u |
| `--tpl` | `channels.txt` | 频道模板（分组 + 频道名） |
| `--only` | — | 只测规范化后以此开头的频道，如 `--only CCTV` |
| `--min-mbps` | `1.5` | 及格线。低于此值不入选（每台仍保留最快 1 条，避免整台消失） |
| `--per-channel` | `5` | 每台最多保留几条线路 |
| `--workers` | `6` | 并发数。**不要调太高**，并发互相抢带宽会导致全部测不准 |
| `--seconds` | `3` | 单条采样时长（秒）。调大更准但更慢 |
| `--limit` | `0` | 只测前 N 条，快速试跑用 |
| `--out` | `output/result_时间戳.txt` | 输出路径 |

**`--min-mbps 1.5` 的含义**：1080p HLS 直播一般需要 2~4 Mbps，720p 需要 1~2 Mbps。
1.5 Mbps 是"能看但可能偶尔缓冲"的下限。想更严格用 `2.5`，想多留线路用 `0.8`。

## 5. 输出怎么用

生成的 `output/result_*.txt` 就是标准直播源 txt：

- **FongMi/TV**：把文件放到盒子上，或用局域网 HTTP 分享后在播放器里填地址；
- 格式与 iptv-api 一致（`分组,#genre#` + `台名,url`），任何支持 txt/m3u 的播放器都能读。

`samples/curated.txt` 是我这边（湖北移动家宽）实测的结果，可作对比基准：
如果同一环境下你测出的速率和它差很多，先怀疑是不是走了代理或被其他程序抢了带宽。

## 6. 故障排查

| 现象 | 原因与处理 |
|---|---|
| 全部 0 Mbps，提示"解析播放列表失败" | 网络不通或走了代理。确认能直接访问目标 IP，关掉系统代理/VPN |
| 部分台 0 Mbps | 该源本身死了或对你的运营商不可达，属正常，换 `--subscribe` 重新建池 |
| 速率普遍偏低（<1 Mbps） | 测速时其他程序在占用带宽，或 `--workers` 设太高，降到 4 再试 |
| `--subscribe` 抓源失败 | 本地访问 GitHub 受限，脚本会自动尝试 gh-proxy / ghfast / jsDelivr 镜像；都失败就改用方式 A |
| 想加台/减台 | 编辑 `channels.txt`（`分组,#genre#` 开头，每行一个台名），再跑 |

## 7. 文件清单

```
speedtest.py       主脚本：建池 → 归类 → 实测 → 排序 → 输出
subscribe.txt      订阅源清单（12 个社区源，可编辑）
channels.txt       频道模板（央视18/卫视34/广东11/凤凰4）
pool.txt           源池快照（3256 条去重线路，免联网即可测）
samples/
  user_result.txt  云端候选池样本（171 条，云端排序的原始产物）
  curated.txt      本机实测精选样本（91 条 / 58 台，可作对比基准）
hubei_mobile.txt   湖北移动 IPTV 网关实测清单（26 个可用频道号）
enum_hls.py        枚举 IPTV 网关的频道号（找同省源用）
ts_sdt.py          从 TS 流里读频道名（SDT 表解析）
find_ip_seg.py     按 IP 段筛源（如只找湖北移动段）
run.bat / run.sh   Windows / Linux 启动器
output/            运行后生成
```

## 8. 附：湖北移动网关发现

`120.40.39.246:352`（湖北移动段）是一个 IPTV 转 HLS 网关，枚举 1~60 号可用 26 个，
实测 **5.65~12.49 Mbps**，详情见 `hubei_mobile.txt`。

编号 1~17 按 IPTV 惯例推断为 CCTV-1~17（其中 `hls/3` 已由源池交叉确认为 CCTV-3），
但 18 号以上无法从编号推出，SDT 里也只有编码器默认名 `Service01`。
建议按 `hubei_mobile.txt` §3 的测试清单在盒子上逐个确认后回填。

## 9. 边界

- 仅个人自用，不公开转发结果文件、不对外提供服务。
- 第三方转播网关随时可能关停，失效后重新枚举即可。
