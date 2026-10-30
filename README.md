# iptv —— 直播源订阅

零本机部署：GitHub Actions 云端产候选池，本机移动家宽实测精选，供 Android 7 电视盒 FongMi/TV 订阅。

> **完整手册已归档**：`E:\workbuddy\.workbuddy\memory\archive\iptv.md`（根因分析、踩坑清单、全部工具说明）。
> 本文件只保留当前状态与日常操作。

## 当前订阅地址

```
主   https://gh-proxy.com/github.com/lanternook/iptv/raw/main/output/curated.txt
备   https://ghfast.top/https://raw.githubusercontent.com/lanternook/iptv/main/output/curated.txt
```

仓库 https://github.com/lanternook/iptv ，工作流 `Update playlist` 每日北京 06:00 / 18:00 跑，只更新候选池。

## 两个文件的分工

| 文件 | 作用 | 更新 |
|---|---|---|
| `output/user_result.txt` | 云端候选池（海外测速，仅素材） | Actions 自动 |
| `output/curated.txt` | **实测精选，唯一可用的订阅** | 本机测速后手动推 |

## 定稿状态（2026-10-31）

- 96 条 / 央视 18 台 42 条 + 卫视 35 台 52 条（含广州综合），凤凰与广东组已按实测删除
- 央视 17 台首条走湖北移动网关 `120.40.39.246:352`（同省，延迟低），咪咕为备选；CCTV-17 网关号 18
- **网关编号 ≠ 台号**：实测 CCTV-1~6 对齐，CCTV-9 起错位（CCTV-9→hls/10，CCTV-17→hls/18）。正确映射见 `config/extra_hubei.txt`
- `config/url_blacklist.txt` 8 条关键字：过滤 TVU 彩条测试卡、编号错位的 txiptv tsfile 流、无法验证的短链
- 网关频道号会变，失效时重跑 `tools/enum_hls.py` 核对

## 日常操作

```bash
cd E:/workbuddy/iptv
python tools/local_speedtest.py --from-subscribe --extra config/extra_hubei.txt --seconds 3   # 重建，约 5 分钟
python tools/merge_tv.py --drop-group 凤凰频道 --drop-group 广东频道 --move 广州综合=卫视频道   # 以电视实测为底合并网关
python tools/push_file.py output/curated.txt --message "curated: 刷新"
python tools/verify_feed.py                                                                    # 推送后校验（等 5 分钟再跑）
```

## 三条硬规则

1. 测速必须在本机直连做，云端结果对国内无参考价值。
2. HLS 测速要解析到 `.ts` 分片，采样 3 秒（2 秒会误判启动慢的源）。
3. 推送后镜像有约 5 分钟缓存，核对内容要比起 md5，不能只看 HTTP 200。

## 目录

```
config/     模板、订阅源、黑名单、网关映射
tools/      测速/合并/枚举/校验/推送 全套脚本
output/     结果与地址清单（pool.txt 为源池快照）
handoff/    交接包源目录（可拷到其他环境跑测速）
dist/       交接包 zip
```
