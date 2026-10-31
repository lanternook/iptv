# iptv —— 直播源订阅

供 Android 7 电视盒 FongMi/TV 订阅。仓库仅作静态托管，**云端 Actions 已停用**，订阅只由本机维护后推送。

## 订阅地址

```
主   https://gh-proxy.com/github.com/lanternook/iptv/raw/main/output/curated.txt
备   https://ghfast.top/https://raw.githubusercontent.com/lanternook/iptv/main/output/curated.txt
```

## 入口

| 文件 | 说明 |
|---|---|
| `update.bat` | **主入口**。双击即跑：体检 → 换血 → 推送 → 校验 |
| `refresh.bat` | 历史入口名，**功能与 update.bat 完全一致**（内部直接转调 update.bat），保留仅为兼容旧习惯 |

两者都接受相同参数：

```bat
update.bat                :: 默认：体检现有线路 + 换血 + 推送（约 2 分钟）
update.bat --dry          :: 只预览，不写文件不推送
update.bat --no-push      :: 生成但不上传
update.bat --apply output\measured.txt   :: 用测速机结果换血（约 10 秒）
update.bat --rebuild      :: 全量重建：联网抓源池 + 全量测速（5~10 分钟）
update.bat --rebuild --from-pool          :: 用本地 output\pool.txt 全量测速，不联网抓源
```

## 架构一句话

**体检 + 换血**，不是重建。日常只测 `output/curated.txt` 里现有的线路，失效的从 `rates.tsv`（无则 `pool.txt`）补，其余保持原样（网关置首、顺序、分组都不动）。

- 测速机（与电视同网络）：双击 `handoff\check.bat`，只测速，产出 `measured.txt`
- 维护机：`update.bat --apply output\measured.txt` 换血并推送

## 文档

- **操作说明**：`docs/操作说明.md`（步骤、脚本职责、故障处理）
- 测速机包说明：`handoff/README.md`
- 完整手册（含根因分析、踩坑清单）：`E:\workbuddy\.workbuddy\memory\archive\iptv.md`

## 目录

```
update.bat / refresh.bat   双击入口（refresh 转调 update）
config/                    模板、订阅源、网关映射、黑名单、推送配置 publish.json
tools/                     全部脚本（pipeline.py 为调度中心）
output/                    curated.txt（订阅）、measured.txt、rates.tsv、pool.txt、logs/
docs/                      操作说明
handoff/ + dist/*.zip      测速机交接包
old/                       【仓库内】已停用的上游源码，不参与流程
```

## 三条硬规则

1. 测速必须直连，不走代理，不边测边看视频。
2. HLS 要解析到 `.ts` 分片再计时，采样 3 秒。
3. 推送后镜像有约 5 分钟缓存，核对要比 md5/字节数。
