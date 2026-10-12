#!/usr/bin/env bash
# Espera a que Railway despliegue un commit en web (adRadio), worker y beat,
# y luego revisa /health y /health/ready en producción.
# Uso: check_deploy.sh <sha-corto-o-largo> [minutos_max=15]
set -u
SHA="${1:?falta el sha del commit}"
SHA="${SHA:0:7}"
MAX_MIN="${2:-15}"
SERVICES=(adRadio worker beat)
deadline=$(( $(date +%s) + MAX_MIN * 60 ))

status_of() {
  timeout 30 railway deployment list -s "$1" --limit 5 --json 2>/dev/null | python3 -c "
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    print('ERROR_CLI'); sys.exit()
for r in rows:
    if (r.get('meta') or {}).get('commitHash', '').startswith('$SHA'):
        print(r['status']); break
else:
    print('PENDIENTE')
"
}

while :; do
  all_ok=1; line=""
  for s in "${SERVICES[@]}"; do
    st=$(status_of "$s")
    line+="$s=$st "
    case "$st" in
      SUCCESS) ;;
      FAILED|CRASHED) echo "❌ $line"; echo "Revisa: railway logs -s $s --deployment"; exit 1 ;;
      *) all_ok=0 ;;
    esac
  done
  echo "$(date +%H:%M:%S) $line"
  [ $all_ok = 1 ] && break
  if [ "$(date +%s)" -ge "$deadline" ]; then echo "⏱️  Se pasó de ${MAX_MIN} min sin terminar"; exit 2; fi
  sleep 30
done

health=$(curl -s -o /dev/null -w '%{http_code}' -m 20 https://www.iaradio.online/health)
ready=$(curl -s -m 20 -w ' %{http_code}' https://www.iaradio.online/health/ready)
echo "/health → $health"
echo "/health/ready → $ready"
[ "$health" = "200" ] && [ "${ready##* }" = "200" ] && echo "✅ Desplegado $SHA en web, worker y beat" && exit 0
echo "❌ Desplegó pero producción no responde bien"; exit 3
