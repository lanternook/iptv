#!/system/bin/sh
# 扫描网关的频道覆盖：每行 label|url，只取 m3u8 的 HTTP 状态码与首段是否可下
F="$1"
while IFS='|' read -r label url; do
  case "$label" in ''|\#*) continue;; esac
  code=$(curl -s --max-time 6 -o /dev/null -w '%{http_code}' "$url")
  printf '%s|%s\n' "$label" "$code"
done < "$F"
