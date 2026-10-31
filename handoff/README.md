# 测速机交接包

这台机器**只做一件事**：体检当前订阅里的线路，看哪些还活着。
不建池、不合并、不改网关、不上传——那些都在维护机上做。

## 怎么用

1. 双击 `check.bat`（约 1 分钟）
2. 把生成的 `measured.txt` 拷回维护机，覆盖 `E:\workbuddy\iptv\output\measured.txt`
3. 在维护机上执行：

```bash
cd E:\workbuddy\iptv
python tools\pipeline.py --apply output\measured.txt
```

维护机会自动把失效的线路换掉、补源、推送上线。

## 要求

- Python 3.8+，无第三方库
- **不要走代理**，测速期间别看视频或下载
- 与电视在同一网络（这样测出来的速度才等于电视的真实体验）

## 产物

| 文件 | 说明 |
|---|---|
| `measured.txt` | 仍可用的线路（保持原分组与顺序），**这个要拷回维护机** |
| `report.tsv` | 全部线路的实测值（台名 / Mbps / 备注 / URL），供人工排查 |

## 可选参数

```bat
check.bat                      :: 先拉 GitHub 最新订阅再测（推荐）
check.bat --src curated.txt    :: 只测包内自带的 curated.txt，不联网拉
check.bat --min-mbps 0.3       :: 提高存活门槛（默认 0.1，只判死链）
check.bat --workers 12         :: 加大并发（默认 8）
```

## 包里其它文件

| 文件 | 用途 |
|---|---|
| `curated.txt` | 打包时的订阅快照，`--pull` 失败时作为兜底 |
| `local_speedtest.py` | 测速函数库，被 check_speed.py 调用，勿删 |
| `speedtest.py` / `run.bat` | 旧的全量重建脚本，本流程用不到，保留备用 |
| `enum_hls.py` | 网关换号时枚举频道号（维护机上也有一份） |
| `ts_sdt.py` / `find_ip_seg.py` | 诊断辅助 |
| `pool.txt` | 源池快照 |
| `samples/` | 历史结果，供对比 |
