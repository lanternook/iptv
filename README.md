# iptv —— 自建直播源工具链

一套**找源 → 测速 → 判活 → 合并 → 上传**的完整方案，供 Android 电视盒（FongMi / TV 等）订阅。
仓库同时作静态托管：`output/curated.txt` 就是订阅文件。

> **先读 [`docs/经验总结.md`](docs/经验总结.md)。**
> 里面的结论几乎全都与直觉相反——照直觉写的脚本会得到完全错误的结论。
> 尤其是「冻结快照」和「本机不可达 ≠ 源失效」两条，不知道就会白干几小时。

## 订阅地址

把 `your-github-user` / `your-iptv-repo` 换成你自己的仓库：

```
主   https://gh-proxy.com/github.com/your-github-user/your-iptv-repo/raw/main/output/curated.txt
备   https://ghfast.top/https://raw.githubusercontent.com/your-github-user/your-iptv-repo/main/output/curated.txt
```

## 快速开始

```bash
# 1. 配置账号（两个 example 文件复制成实例后填写）
cp config/publish.example.json config/publish.json
cp tools/site.example.json     tools/site.json

# 2. 写 GitHub PAT（fine-grained，需 Contents 读写权限）
echo "ghp_xxxxxxxx" > tools/token.txt

# 3. 跑一遍完整流水线
python tools/pipeline.py
```

`config/publish.json`、`tools/site.json`、`tools/token.txt` 都已在 `.gitignore` 中排除，不会入库。

## 入口

| 文件 | 说明 |
|---|---|
| `update.bat` | **主入口**。双击即跑：体检 → 换血 → 推送 → 校验 |
| `refresh.bat` | 历史入口名，功能与 `update.bat` 完全一致（转调），保留仅为兼容旧习惯 |
| `find_gateway.bat` | 找新网关 |
| `phone_speed.bat` | 生成手机端测速任务 |

```bat
update.bat                :: 默认：体检现有线路 + 换血 + 推送（约 2 分钟）
update.bat --dry          :: 只预览，不写文件不推送
update.bat --no-push      :: 生成但不上传
update.bat --apply output\measured.txt   :: 用测速机结果换血（约 10 秒）
update.bat --rebuild      :: 全量重建：联网抓源池 + 全量测速（5~10 分钟）
update.bat --rebuild --from-pool          :: 用本地 output\pool.txt 全量测速，不联网抓源
```

## 流水线五步

| 步 | 命令 | 要点 |
|---|---|---|
| ① 找源 | `python tools/find_gateway.py` | 扫网关池 / 订阅池 |
| ② 测速 | `python tools/phone_speed.py` | **必须用目标设备测**，本机结果只判活不排序 |
| ③ 判活 | `python tools/audit_live.py output/curated.txt --wait 14` | 比对 `MEDIA-SEQUENCE` 指纹，抓冻结快照 |
| ④ 合并 | `python tools/merge_tv.py` → `fix_by_audit.py --apply` | 去重、排序、补缺口，每台留 3 条冗余 |
| ⑤ 上传 | `python tools/gh_api.py push output/curated.txt` | 走系统代理，失败先怀疑代理 |

## 三条硬规则

1. 测速必须直连，不走代理，不边测边看视频。
2. HLS 要解析到 `.ts` 分片再计时，采样 3 秒。
3. 推送后镜像有约 5 分钟缓存，核对要比 md5 / 字节数。

## 目录

```
update.bat / refresh.bat   双击入口（refresh 转调 update）
find_gateway.bat           找网关入口
phone_speed.bat            手机测速入口
config/                    网关池、订阅源、黑名单、发布配置模板
tools/                     全部脚本（64 个，pipeline.py 为调度中心）
output/                    curated.txt（订阅）、rates.tsv、pool.txt、logs/
docs/                      经验总结.md、操作说明.md
handoff/                   测速机交接包
old/                       已停用的上游源码，不参与流程
```

## 工具分组

| 阶段 | 脚本 |
|---|---|
| 找源 | `find_gateway` `find_ip_seg` `find_source` `fill_gateways` `reorder_gateways` `scan_pool` `scan_cztv` `scan_xwl` `enum_hls` `iptv_url_gen` `ip_owner` `proxy_probe` |
| 官方源探测 | `probe_cctv_cdn` `probe_cctv_stream` `probe_cntv_api` `probe_ysp*` `ysp_live` `apk_dex_str` `apk_manifest` `promote_cdn` `verify_cztv_live` |
| 测速 | `check_speed` `local_speedtest` `phone_speed` `speed_multi` `measure_primary` `verify_feed` `check_subs` |
| 判活 | `audit_live` `fix_by_audit` |
| 合并 | `merge_tv` `phone_merge` `apply_phone_speed` `apply_measured` `fix_cctv` `fill_missing` `purge_dead` `reorder_by_phone` `num_map` `to_m3u` `make_sheet` |
| 抓帧核验 | `grab_frames` `grab_frames2` `ts_sdt` |
| 上传 | `gh_api` `push_file` `bootstrap_repo` `watch_run` `pipeline` |

## 文档

- **[经验总结](docs/经验总结.md)** —— 踩坑清单，先读这个
- [操作说明](docs/操作说明.md) —— 步骤、脚本职责、故障处理
- [测速机包说明](handoff/README.md)
