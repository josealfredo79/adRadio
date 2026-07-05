# Procedimiento de Rollback — IaRadio

Si un deploy a produccion causa problemas, sigue estos pasos para revertir.

## Rollback rapido (1 min)

```bash
# 1. Identificar el commit problemático
git log --oneline -5

# 2. Revertir el commit
git revert <commit-hash> --no-edit

# 3. Push a origin (Railway redeploya automatico)
git push origin master
```

Railway detecta el push y redeploya en ~2 minutos.

## Verificar despues del rollback

```bash
# Health check
curl https://www.iaradio.online/health
# Debe retornar: {"status":"ok"}

# Verificar que el frontend carga
curl -s -o /dev/null -w "%{http_code}" https://www.iaradio.online
# Debe retornar: 200
```

## Rollback de base de datos (si hay migracion)

Si el commit incluyo una migracion de Alembic:

```bash
# 1. Revertir el commit (esto revierte el codigo)
git revert <commit-hash> --no-edit
git push origin master

# 2. Revolver la migracion en Neon
# Conectar a Neon y ejecutar:
alembic downgrade -1
```

**IMPORTANTE:** Solo usar si la migracion rompe datos. Si es una migracion aditiva (columna nueva), el rollback de codigo es suficiente.

## Si el rollback no funciona

1. Verificar logs de Railway: Dashboard > Service > Deployments > Logs
2. Verificar que la migracion de BD no dejo tablas inconsistentes
3. Contactar soporte de Railway si hay problemas de infraestructura
