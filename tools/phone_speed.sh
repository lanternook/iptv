#!/system/bin/sh
# 在手机（移动网络）上测 HLS 速度
# 用法：sh phone_speed.sh /data/local/tmp/urls.txt
# 输入每行：label|url
# 输出每行：label|Mbps|httpcode|segbytes
F="$1"
[ -z "$F" ] && { echo "no file"; exit 1; }
while IFS='|' read -r label url; do
  case "$label" in ''|\#*) continue;; esac
  base=$(echo "$url" | sed 's#/[^/]*$##')
  pl=$(curl -s --max-time 8 "$url")
  seg=$(echo "$pl" | grep -v '^#' | grep -v '^[[:space:]]*$' | head -1 | tr -d '\r')
  if [ -z "$seg" ]; then
    echo "$label|0.00|000|m3u8fail"
    continue
  fi
  case "$seg" in
    http*) ts="$seg" ;;
    /*)    ts="$(echo "$url" | sed 's#\(https\?://[^/]*\).*#\1#')$seg" ;;
    *)     ts="$base/$seg" ;;
  esac
  res=$(curl -s --max-time 4 -o /dev/null -w '%{speed_download} %{http_code} %{size_download}' "$ts")
  sp=$(echo "$res" | awk '{printf "%.2f", $1*8/1000000}')
  code=$(echo "$res" | awk '{print $2}')
  sz=$(echo "$res" | awk '{print $3}')
  echo "$label|$sp|$code|$sz"
done < "$F"
