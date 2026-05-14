# Railway - Solución de Problemas

## 502 Application Failed to Respond

**Problema**: Después de varios deploys fallidos, la app responde 502 aunque los logs muestran healthcheck 200 OK.

**Solución**: Eliminar el servicio en Railway y crear uno nuevo desde cero.

Pasos:
1. Eliminar el servicio "web" en Railway
2. Crear nuevo servicio: New → Deploy from GitHub
3. Agregar variables de entorno
4. Deploy automático

**Nota**: El código estaba bien - el problema era estado corrupto en Railway.

---

## Configuración actual

- Puerto: 8080
- Dockerfile usa `/docker-entrypoint.sh`
- railway.json tiene `targetPort: 8080`