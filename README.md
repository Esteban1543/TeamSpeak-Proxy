# TS3 Proxy Panel

Panel web para crear redirecciones UDP hacia servidores de **TeamSpeak 3** desde una VPS.

El administrador escribe el destino (`IP`, `IP:puerto` o un dominio) y el panel devuelve
`IP_DE_LA_VPS:puerto_nuevo`. Los usuarios se conectan en TS3 a esa dirección sin instalar
nada, y el servidor de TeamSpeak ve la IP de la VPS en lugar de la del usuario.

```
Cliente TS3 ──UDP──▶ VPS:10023 ──UDP──▶ ts.ejemplo.com:9987
            ◀──────            ◀──────
```

## Características

- Acceso solo para un administrador (usuario + contraseña con bcrypt, cookie HttpOnly).
- Rango de puertos limitado y configurable; el puerto se libera al eliminar la redirección.
- Resolución de dominios como el cliente de TS3: registro SRV `_ts3._udp.<dominio>`, y si no
  existe, A/AAAA. Los dominios se vuelven a resolver periódicamente.
- Las redirecciones se guardan en SQLite y se vuelven a levantar automáticamente al reiniciar.
- Estadísticas por redirección: clientes conectados y tráfico.

## Estructura

```
backend/    FastAPI + proxy UDP asyncio/uvloop + SQLite
frontend/   Astro (estático) + Tailwind + nanostores
Caddyfile   Sirve el frontend y redirige /api al backend (HTTPS automático)
docker-compose.yml
data/       Base de datos SQLite (volumen)
```

## Requisitos

- Una VPS Linux con IP pública (Ubuntu/Debian recomendados).
- Docker Engine 24+ con el plugin Docker Compose v2.
- Opcional: un dominio (p. ej. `panel.tudominio.com`) con un registro A apuntando a la VPS,
  para tener HTTPS.

## Instalación en la VPS

### 1. Copiar el proyecto

```bash
git clone <tu-repositorio> ts3-proxy && cd ts3-proxy
# o súbelo con scp/rsync
```

### 2. Crear los archivos `.env`

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

- **`.env`** (raíz): `DOMAIN=panel.tudominio.com`. Déjalo vacío (`DOMAIN=`) si vas a
  entrar por `http://IP_DE_LA_VPS`.
- **`backend/.env`**: como mínimo `PUBLIC_HOST` (la IP pública de la VPS),
  `PORT_RANGE_START`/`PORT_RANGE_END`, `ADMIN_PASSWORD_HASH` y `SESSION_SECRET`
  (siguiente paso).
- **`frontend/.env`**: normalmente no hace falta cambiarlo. Solo admite variables `PUBLIC_*`,
  que se insertan al compilar y son visibles en el navegador: **nunca pongas secretos ahí**.

### 3. Generar el hash de la contraseña

```bash
docker compose build backend
docker compose run --rm backend python -m app.hash_password
```

El comando pide la contraseña dos veces e imprime algo como:

```
ADMIN_PASSWORD_HASH='$2b$12$....'
SESSION_SECRET=Yx3...
```

Copia ambas líneas en `backend/.env`. **Mantén las comillas simples** del hash: contiene `$`
y Docker Compose lo interpretaría como una variable.

Sin Docker (con Python 3.12+): `cd backend && pip install bcrypt && python -m app.hash_password`.

> Cambiar la contraseña invalida todas las sesiones abiertas.

### 4. Abrir puertos en el firewall

Hay que abrir **el rango UDP** de las redirecciones y **80/443 TCP** para el panel.

**ufw** (en la VPS):

```bash
sudo ufw allow OpenSSH            # ¡antes de activar ufw!
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 10000:10100/udp    # el mismo rango que PORT_RANGE_START:PORT_RANGE_END
sudo ufw enable
sudo ufw status
```

**Panel del proveedor**: muchos proveedores (Hetzner, OVH, AWS, Oracle Cloud, Google Cloud,
DigitalOcean…) tienen un firewall propio delante de la VPS (“Security Group”, “Firewall”,
“Network ACL”). Añade allí las mismas reglas de entrada:

| Protocolo | Puertos       | Origen    |
|-----------|---------------|-----------|
| TCP       | 22            | tu IP     |
| TCP       | 80, 443       | 0.0.0.0/0 |
| UDP       | 10000-10100   | 0.0.0.0/0 |

> El puerto de la API (8000) **no** debe abrirse: solo escucha en `127.0.0.1` y Caddy
> la expone bajo `/api`.

### 5. Arrancar

```bash
docker compose up -d --build
docker compose logs -f
```

Abre `https://panel.tudominio.com` (o `http://IP_DE_LA_VPS`).

#### Acceso sin dominio (HTTP)

Sin HTTPS, el navegador no envía cookies marcadas como `Secure`. Si accedes por
`http://IP`, pon en `backend/.env`:

```env
SESSION_COOKIE_SECURE=false
```

y reinicia con `docker compose up -d`. Se recomienda usar un dominio con HTTPS: sin él, la
contraseña y la cookie viajan sin cifrar.

## Uso del panel

1. Inicia sesión con `ADMIN_USER` y la contraseña elegida.
2. Escribe el destino en el formulario y pulsa **Crear redirección**:
   - `ts.ejemplo.com` → se consulta el SRV `_ts3._udp.ts.ejemplo.com`; si no existe, A/AAAA
     con el puerto 9987.
   - `ts.ejemplo.com:9988` → A/AAAA con ese puerto (sin SRV).
   - `1.2.3.4` → puerto 9987. `1.2.3.4:9988` → ese puerto.
   - IPv6: `[2001:db8::1]:9987`.
3. El panel muestra la **dirección pública** (`IP_VPS:puerto`). Haz clic en ella para
   copiarla y compártela con los usuarios: es lo que deben escribir en TeamSpeak 3.
4. El indicador superior muestra los puertos usados (p. ej. `23 / 100`). Cuando se agota el
   rango no se pueden crear más redirecciones hasta eliminar alguna.
5. **Eliminar** detiene el proxy y libera el puerto inmediatamente.

Estados de una redirección:

| Estado     | Significado                                                                 |
|------------|-----------------------------------------------------------------------------|
| Activa     | El proxy está escuchando y reenviando tráfico.                              |
| Pendiente  | Guardada, a la espera de arrancar el proxy.                                 |
| Error      | El proxy no pudo arrancar (p. ej. otro programa usa el puerto). Se reintenta cada 30 s. |
| Detenida   | Reservado para pausar redirecciones.                                        |

## Funcionamiento interno

- **Proxy UDP (asyncio + uvloop)**: escucha en el puerto asignado y crea un socket de salida
  por cada cliente (IP:puerto de origen), así las respuestas vuelven al cliente correcto.
  Las sesiones sin tráfico durante `CLIENT_IDLE_TIMEOUT` segundos (120 por defecto) se cierran.
- **Reconciliador**: al arrancar levanta todas las redirecciones guardadas; cada 30 s relanza
  proxies caídos y cada `DNS_REFRESH_MINUTES` vuelve a resolver los dominios. Si la IP cambia,
  el proxy pasa a usar la nueva. Si la resolución falla, se mantiene la última IP conocida.
- **Asignación de puertos**: en una única transacción SQLite (`BEGIN IMMEDIATE`) con
  restricción `UNIQUE` en el puerto, para que dos peticiones simultáneas nunca reciban el mismo.
- `network_mode: host` en el backend: publicar rangos UDP grandes con `ports:` es lento,
  añade latencia, y el proxy necesita abrir puertos dinámicamente. Caddy también usa la red
  del host para acceder a la API en `127.0.0.1:8000`.

## Variables de entorno del backend

| Variable                | Por defecto       | Descripción                                               |
|-------------------------|-------------------|-----------------------------------------------------------|
| `API_HOST`              | `127.0.0.1`       | Interfaz de la API (no cambiar con `network_mode: host`). |
| `API_PORT`              | `8000`            | Puerto de la API (no puede estar dentro del rango).       |
| `DATABASE_PATH`         | `/data/proxy.db`  | Ruta de SQLite dentro del contenedor.                     |
| `PORT_RANGE_START/END`  | `10000`/`10100`   | Rango de puertos UDP (incluidos). `END` > `START`.        |
| `PUBLIC_HOST`           | —                 | IP o dominio público mostrado a los usuarios.             |
| `ADMIN_USER`            | `admin`           | Usuario administrador.                                    |
| `ADMIN_PASSWORD_HASH`   | —                 | Hash bcrypt (`python -m app.hash_password`).              |
| `SESSION_SECRET`        | —                 | Clave para firmar la cookie (≥ 32 caracteres).            |
| `SESSION_EXPIRE_HOURS`  | `12`              | Duración de la sesión.                                    |
| `SESSION_COOKIE_SECURE` | `true`            | `false` solo si se accede por HTTP.                       |
| `DNS_REFRESH_MINUTES`   | `10`              | Intervalo de re-resolución de dominios.                   |
| `FORWARDING_ENGINE`     | `asyncio`         | `nftables` está reservado (no implementado).              |
| `CLIENT_IDLE_TIMEOUT`   | `120`             | Segundos de inactividad antes de cerrar la sesión de un cliente. |

Si alguna variable es incorrecta, el backend no arranca y muestra qué falla
(`docker compose logs backend`).

## Limitaciones conocidas

- **Transferencia de archivos (TCP 30033)**: el cliente TS3 abre la transferencia de
  archivos contra la misma IP a la que se conecta, en el puerto TCP 30033 (o el que indique
  el servidor). Como este proxy solo reenvía UDP, en las redirecciones **funcionan voz y
  chat, pero puede que no carguen avatares, iconos ni archivos**. Como mucho, una sola
  redirección por VPS podría tener esa función, reenviando a mano el TCP 30033 hacia su
  servidor.
- **Bloqueo de IPs de datacenter/VPN**: algunos servidores TS3 bloquean rangos de IPs de
  proveedores de hosting o VPN. Para ellos todos los usuarios del proxy comparten la IP de la
  VPS, así que un ban o un límite de conexiones por IP afecta a todos a la vez.
- Los usuarios aparecen en el servidor con la IP de la VPS: las herramientas del servidor
  que dependen de la IP real (bans por IP, geolocalización) dejan de distinguirlos.
- El reenvío se hace en espacio de usuario; para cientos de usuarios simultáneos, el motor
  `nftables` (pendiente) reduciría latencia y CPU. Requeriría `cap_add: [NET_ADMIN]`.

## Desarrollo

```bash
# Backend (Python 3.12+)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
DATABASE_PATH=../data/proxy.db python -m app.main     # usa backend/.env

# Frontend (Node 22.12+) — /api se redirige a 127.0.0.1:8000
cd frontend
npm install
npm run dev
```

Documentación interactiva de la API: `/api/docs`.

## Copias de seguridad y actualización

```bash
# Copia de seguridad de la base de datos
cp data/proxy.db data/proxy.db.bak

# Actualizar
git pull && docker compose up -d --build
```
