# Despliegue: Cloud Run + Cloud SQL (PostgreSQL)

El backend corre en Cloud Run y llega a Cloud SQL por el socket unix que Cloud Run monta en
`/cloudsql/<conexión>` — la base no se expone a internet ni hace falta abrir IPs. No hay cambios de
código respecto al desarrollo local: sólo variables de entorno.

Reemplazá `PROYECTO`, `REGION` y `INSTANCIA` (ej. `mi-proyecto:southamerica-east1:aisec-db`).

## 1. Cloud SQL

```bash
gcloud sql instances create aisec-db --database-version=POSTGRES_16 --region=REGION --tier=db-custom-1-3840
gcloud sql databases create aisec --instance=aisec-db
gcloud sql users create aisec_app --instance=aisec-db --password='<clave>'
```

## 2. Secretos (Secret Manager)

```bash
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create aisec-jwt-secret --data-file=-
printf '%s' 'postgresql+psycopg://aisec_app:<CLAVE_URL_ENCODED>@/aisec?host=/cloudsql/PROYECTO:REGION:INSTANCIA' \
  | gcloud secrets create aisec-database-url --data-file=-
printf '%s' '<sk-...>' | gcloud secrets create aisec-openai-key --data-file=-
```

La contraseña dentro de la URL va **URL-encoded** (`@` → `%40`, `/` → `%2F`, `:` → `%3A`).
Fuera de `development` el backend se niega a arrancar con el `JWT_SECRET` por defecto o de menos de
32 caracteres.

## 3. Build y deploy

```bash
gcloud run deploy aisec-backend --source backend --region REGION \
  --add-cloudsql-instances PROYECTO:REGION:INSTANCIA \
  --set-env-vars AISEC_ENVIRONMENT=production,AISEC_LLM_PROVIDER=openai,AISEC_CORS_ALLOWED_ORIGINS=https://<frontend> \
  --set-secrets AISEC_DATABASE_URL=aisec-database-url:latest,AISEC_JWT_SECRET=aisec-jwt-secret:latest,AISEC_OPENAI_API_KEY=aisec-openai-key:latest \
  --max-instances 5
```

**Conexiones.** Cada instancia abre un pool de `AISEC_DB_POOL_SIZE` (5) + `AISEC_DB_MAX_OVERFLOW`
(2) conexiones. `max-instances × 7` debe quedar por debajo de `max_connections` de la instancia de
Cloud SQL (depende del tier, verificalo con `SHOW max_connections;`; los tiers chicos son de decenas). Ajustá `--max-instances` o el pool según corresponda.

## 4. Migraciones y primer admin (Cloud Run Jobs)

Se usa la misma imagen, cambiando el comando. Correr **una vez por versión**, antes de que el nuevo
código reciba tráfico — no al arrancar el servicio, para que varias instancias no migren en paralelo.

```bash
IMG=$(gcloud run services describe aisec-backend --region REGION --format='value(spec.template.spec.containers[0].image)')

# Migraciones (en cada release). En una base nueva esto también carga el catálogo de
# 138 preguntas: es una migración de datos, no hace falta ningún paso aparte.
gcloud run jobs create aisec-migrate --image "$IMG" --region REGION \
  --set-cloudsql-instances PROYECTO:REGION:INSTANCIA \
  --set-secrets AISEC_DATABASE_URL=aisec-database-url:latest,AISEC_JWT_SECRET=aisec-jwt-secret:latest \
  --set-env-vars AISEC_ENVIRONMENT=production \
  --command alembic --args upgrade,head
gcloud run jobs execute aisec-migrate --region REGION --wait

# Primer admin (una sola vez); la contraseña viene de un secreto
printf '%s' '<clave-admin>' | gcloud secrets create aisec-admin-password --data-file=-
gcloud run jobs create aisec-bootstrap-admin --image "$IMG" --region REGION \
  --set-cloudsql-instances PROYECTO:REGION:INSTANCIA \
  --set-secrets AISEC_DATABASE_URL=aisec-database-url:latest,AISEC_JWT_SECRET=aisec-jwt-secret:latest,AISEC_BOOTSTRAP_ADMIN_PASSWORD=aisec-admin-password:latest \
  --set-env-vars AISEC_ENVIRONMENT=production \
  --command python --args scripts/bootstrap_admin.py,--username,admin
gcloud run jobs execute aisec-bootstrap-admin --region REGION --wait
```

## 5. Desarrollo local contra Cloud SQL (opcional)

Con el [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/sql-proxy):

```bash
cloud-sql-proxy PROYECTO:REGION:INSTANCIA --port 5434
# backend/.env → AISEC_DATABASE_URL=postgresql+psycopg://aisec_app:<clave>@127.0.0.1:5434/aisec
```

Los tests **no** usan esa base: siempre corren contra una base local `aisec_test`
(`localhost:5433` por defecto, o `AISEC_TEST_DATABASE_URL`) y se niegan a arrancar si esa URL apunta
a un host que no sea local, porque truncan tablas.

## Pendiente fuera de este repo

- Hosting del frontend (build estático de `frontend/`, con `VITE_API_URL` apuntando al servicio de
  Cloud Run) y el origen correspondiente en `AISEC_CORS_ALLOWED_ORIGINS`.
- Backups y ventana de mantenimiento de la instancia (`gcloud sql instances patch`).
- Si el backend queda público, un mecanismo delante (IAP, Cloud Armor o VPN) — el login local por
  JWT no incluye limitación de intentos.
