# Auditoría de capacidades: cuatro repositorios frente a `android_agent_bridge`

**Fecha:** 2026-09-10
**Alcance:** auditoría estática completa de `pyt-androidtv`, `Flujo_android`, `tvbox-controller` y `movicom`, comparada con el estado actual de `android_agent_bridge`.
**Resultado:** documento de trazabilidad y plan de integración; esta auditoría no copia código de producto ni modifica los repositorios fuente.

## 1. Objetivo y método

El objetivo es determinar, capacidad por capacidad, qué falta en `android_agent_bridge`, qué debe integrarse, qué debe descartarse y qué necesita un adapter separado. La comparación no trata los cuatro proyectos como implementaciones equivalentes:

- `android_agent_bridge` es el núcleo agent-first y debe conservar un único transporte ADB, una única sesión UI y frames compactos.
- `pyt-androidtv` aporta principalmente capacidades generales de dispositivo Android TV/Fire TV.
- `Flujo_android` aporta automatización y extracción específica de MGAndroid.
- `tvbox-controller` aporta una fachada MGAndroid, REST y proveedores opcionales de percepción, aunque varias rutas declaradas no están implementadas.
- `movicom` aporta el patrón agent-first y herramientas genéricas de sistema, web, contactos, notificaciones y workflows.

Se revisaron los archivos de código, configuración, documentación, pruebas y despliegue de los cuatro repositorios, además del núcleo, adapters, documentación y knowledge pack actuales del bridge. La auditoría es estática: no afirma compatibilidad con un APK o dispositivo real que no haya sido validada con fixtures o ejecución controlada.

### Clasificaciones

- **NUEVO:** no existe una capacidad equivalente en el bridge.
- **MEJORA:** existe una base, pero no cubre el comportamiento o la robustez observada.
- **DUPLICADO:** la capacidad ya existe con el mismo propósito y no debe portarse otra vez.
- **VARIANTE:** existe solapamiento, pero cambia el contrato, alcance o capa.
- **CONTRADICTORIO:** la documentación o una implementación declara algo que el código real no cumple, o que contradice el contrato del bridge.
- **FUERA_DE_ALCANCE:** pertenece a Home Assistant, Docker, UI de despliegue u otra integración separada.
- **NO_DECIDIBLE:** requiere dispositivo, versión de APK, red o prueba de runtime para concluir.

## 2. Estado actual de `android_agent_bridge`

El bridge ya contiene:

- `SubprocessADB` con serial opcional, timeout, shell tipado, dump UI, tap, keyevent, swipe e input text.
- `AndroidDevice` para foreground, aplicaciones launchables, apertura de aplicaciones y snapshots.
- Parser de UI Automator con árbol padre/hijo, atributos normalizados y bounds del ancestro clickeable.
- `FrameBuilder` para frames compactos, acciones numeradas y paginación.
- `UISession` persistente con ciclo `read → do → read`.
- `KnowledgeRegistry` con resolución por package, alias o identificador.
- Pack inicial de MGAndroid con `manifest.json`, `selectors.json`, `states.json` y `actions.json`.
- Modelo de workflows.
- CLI, REST mínimo y MCP persistente.

El estado importante de la auditoría es el siguiente: el manifest y parte del reconocimiento de estados participan en el runtime, pero `selectors.json` y `actions.json` todavía no son un ejecutor funcional. El bridge tiene el punto de extensión correcto, pero aún debe conectar el conocimiento declarativo con la sesión UI.

## 3. Matriz ejecutiva por repositorio

| Proyecto fuente | Capacidades principales | Clasificación global | Destino recomendado |
|---|---|---|---|
| `pyt-androidtv` | ADB TCP/server, metadatos, power, volumen, multimedia, diagnóstico, wireless y archivos | NUEVO / MEJORA / VARIANTE | `adb/`, `devices/`, `diagnostics/`, `provisioning/` |
| `Flujo_android` | Selector rico, lifecycle MGAndroid, canales, crawler, screenshots, waits y CLI | NUEVO / MEJORA | knowledge pack, `workflows/`, adapter de diagnóstico |
| `tvbox-controller` | Navegación MGAndroid, panel de canales, REST, OCR/CV/LLM y Docker | NUEVO / VARIANTE / CONTRADICTORIO | knowledge pack, workflows, adapters opcionales |
| `movicom` | Protocolo agent-first, system lane, web, contactos, notificaciones, cámara y workflows | NUEVO / MEJORA / CONTRADICTORIO | MCP/system adapters, `workflows/`, policies |

La integración no debe ser una copia de directorios. La arquitectura objetivo es:

```text
MCP / REST / CLI / Home Assistant adapters
                         ↓
              Frame + UISession + workflows
                         ↓
              UI parser + selector resolver
                         ↓
                  Knowledge packs
                         ↓
       AndroidDevice capabilities + diagnostics
                         ↓
                    ADBTransport
```

## 3.1 Matriz detallada de trazabilidad

Esta matriz convierte la comparación narrativa en hallazgos identificables. Cada fila tiene una fuente, una decisión de clasificación, un destino y un criterio observable para considerar la integración terminada. `Estado` describe el bridge en el momento de la auditoría; no significa que el hallazgo ya esté implementado.

| ID | Fuente | Capacidad o hallazgo | Clasificación | Relevancia | Destino | Estado actual | Criterio de aceptación |
|---|---|---|---|---|---|---|---|
| PT-ADB-01 | `pyt-androidtv/src/pyt_androidtv/adb/{base,tcp,server}.py` | ADB TCP, servidor ADB, auth RSA, timeouts, conexión y errores | NUEVO / MEJORA | Alta | `adb/transport.py` y backends | Parcial | Un único contrato permite subprocess, TCP y server con timeouts y errores estructurados; los adapters no crean clientes secundarios |
| PT-ADB-02 | `pyt-androidtv/src/pyt_androidtv/adb/{base,tcp,server}.py` | `pull`, `push` y `screencap` | NUEVO | Alta para diagnóstico | `adb/transport.py` | Falta | Fixtures o fake transport prueban transferencia y captura con paths validados y límites de tamaño |
| PT-DEV-01 | `models.py`, `BaseTV.get_device_properties()` | Fabricante, modelo, serial, Android, product ID y MAC | NUEVO | Alta para doctor | `devices/`, `diagnostics/` | Falta | `android_doctor` devuelve un snapshot sanitizado y no lo mezcla con el frame UI |
| PT-DEV-02 | `BaseTV.get_screen_resolution()`, `get_screen_density()` | Resolución y densidad | NUEVO | Media/alta para adaptación | `devices/` | Falta | El viewport puede consultarse bajo demanda y los swipes no dependen de 540/1080 fijo |
| PT-STATE-01 | `BaseTV.screen_on()`, `awake()`, `wake_lock_size()` | Estado físico de pantalla, wake y wake lock | NUEVO | Alta para recovery | `devices/`, `diagnostics/` | Falta | Se distingue `screen_on`, `awake` e indeterminado con errores tipados |
| PT-STATE-02 | `current_app_media_session_state()`, `audio_state()`, `get_hdmi_input()` | Estado multimedia, audio y HDMI | NUEVO | Alta para TV | `devices/`, `diagnostics/` | Falta | Una consulta explícita devuelve estado multimedia sin alterar `Frame.screen` |
| PT-TV-01 | `BaseTV.stream_music_properties()`, `set_volume_level()` | Lectura y ajuste normalizado de volumen, mute y salida | NUEVO | Alta | `devices/` y tools controladas | Falta | Se valida rango `0.0–1.0`, dispositivo objetivo y resultado; mute no usa shell libre |
| PT-TV-02 | `constants.py`, helpers de teclas y `turn_on/off/sleep()` | DPAD, media, power y sleep | NUEVO / VARIANTE | Alta | `devices/` con allowlist | Parcial: solo `keyevent` genérico | Verbos semánticos seguros generan los keyevents correctos y rechazan códigos no permitidos |
| PT-WIRE-01 | `wireless/discovery.py` | Scan TCP/Zeroconf y candidatos ADB | NUEVO | Media/alta | `provisioning/` | Falta | Un candidato solo se acepta después de validar handshake ADB; el scan es explícito |
| PT-WIRE-02 | `wireless/pairing.py` | Pairing, `adb tcpip`, conexión y reconnect | NUEVO | Media/alta | `provisioning/` | Falta | Pairing requiere aprobación, no imprime códigos y devuelve estado `paired` separado de `connected` |
| PT-DIAG-01 | `diagnostics/{system,network,apps,report}.py` | Memoria, storage, uptime, red, procesos, apps y reportes | NUEVO | Alta para soporte | `diagnostics/` | Parcial: doctor solo es mínimo | Quick doctor y full report son consultas separadas, sanitizadas y bajo demanda |
| PT-FILE-01 | `BaseTV.screen_record()` y ADB `pull/push` | Grabación y artefactos de diagnóstico | NUEVO | Media/alta | `diagnostics/` y adapter aprobado | Falta | Paths, duración, tamaño y retención están limitados; la grabación no bloquea MCP indefinidamente |
| PT-HA-01 | `custom_components/pyt_androidtv/` | Entidades, ConfigFlow, servicios, cámara y Mushroom | FUERA_DE_ALCANCE | Baja para core | Adapter HA futuro | No portar | No existen entidades HA dentro del núcleo ni un segundo cliente ADB |
| FA-SEL-01 | `Flujo_android/selector.py` | Texto, regex, ID parcial, clase, región, jerarquía y predicados | MEJORA / NUEVO | Crítica | `ui/` y `knowledge/` | Parcial: matching básico | Un selector declarativo devuelve un nodo actual, respeta prioridad y explica `selector_not_found` sin exponer XML al LLM |
| FA-MG-01 | `Flujo_android/app.py`, `mgandroid.py` | Open, close, restart, wait-ready y ensure-home | NUEVO | Alta | workflow/policy MGAndroid | Falta | Cada transición tiene timeout, indicadores y frame posterior; recovery no depende solo de `sleep()` |
| FA-MG-02 | `Flujo_android/mgandroid.py` | Live, movies, series, anime, special, settings, history y favorites | NUEVO | Alta | `knowledge/apps/mgandroid/`, `workflows/` | Parcial: acciones declaradas no ejecutables | Cada workflow verifica estado de origen, usa selector fresco y verifica destino |
| FA-CHANNEL-01 | `Flujo_android/channel_extractor.py` | Panel, categorías, canales, EPG, favoritos, selección y deduplicación | NUEVO | Crítica para MGAndroid | pack y workflows | Falta | Se extraen canales por contenedor/ID/jerarquía, sin umbral fijo `left > 300`, y se devuelve evidencia sanitizada |
| FA-CRAWL-01 | `Flujo_android/crawler.py`, `main.py` | Crawl, dumps, screenshots, exportación y CLI de diagnóstico | NUEVO / VARIANTE | Media | adapter de diagnóstico | Falta | El crawler produce evidencia candidata versionada; no modifica packs automáticamente ni entra en el ciclo normal |
| FA-DPAD-01 | `Flujo_android/device.py`, `mgandroid.py` | Navegación DPAD para TV | MEJORA | Alta | `devices/`, `ui/session.py` | Incorrecto: `up/down` usan swipe | `up/down/left/right` usan `KEYCODE_DPAD_*`; `scroll` es una acción independiente |
| TB-MG-01 | `tvbox-controller/mgandroid.py`, `actions.py`, `ids.yaml` | Navegación MGAndroid y estado de app | NUEVO / MEJORA | Alta | pack/workflows | Parcial y duplicado en formato YAML | Solo queda un knowledge pack canónico; la evidencia de `ids.yaml` se normaliza y se prueba |
| TB-CHANNEL-01 | `tvbox-controller/mgandroid.py` | Panel, lista, canal actual, búsqueda y channel up/down | NUEVO | Crítica | workflows MGAndroid | Falta | El workflow abre panel solo si es necesario, selecciona por nombre y devuelve frame verificado |
| TB-PERCEPT-01 | `ocr.py`, `vision.py`, `llm_vision.py`, `engine.py` | OCR/CV/LLM para candidatos visuales | NUEVO / VARIANTE | Media, opcional | providers de percepción | Falta | El proveedor devuelve candidato/confianza; el ejecutor valida frame fresco y nunca recibe shell/coordenadas persistentes |
| TB-REST-01 | `tvbox-controller/app.py` | REST de control y `action` | VARIANTE / CONTRADICTORIO | Media | `adapters/rest.py` | REST bridge mínimo | Endpoints solo llaman capacidades existentes, tienen auth/configuración y errores HTTP estructurados |
| TB-DEPLOY-01 | `Dockerfile`, `docker-compose.yml`, `requirements.txt` | Docker, healthcheck, red y dependencias pesadas | FUERA_DE_ALCANCE / VARIANTE | Media para despliegue | `deploy/` o docs | No existe en core | El despliegue es opcional, parametrizado y no mezcla OCR/CV con dependencias base |
| MV-SYSTEM-01 | `movicom` system lane | App store, intents, URLs, web, contactos, notificaciones y cámara | NUEVO | Media/alta, con aprobación | adapters/system | Falta | Cada tool tiene allowlist, esquema, redacción de datos y aprobación para instalar, contactar, publicar o enviar |
| MV-WORKFLOW-01 | `movicom` workflows | Workflows persistentes ejecutables | NUEVO | Alta | `workflows/` | Solo existe el modelo | Runner reutiliza una `UISession`, reevalúa cada paso y detiene la secuencia ante cambio de estado |
| MV-INPUT-01 | `movicom` y `pyt-androidtv` input helpers | Limpieza, teclado, submit, ENTER, escaping y focus | MEJORA | Alta | `adb/transport.py`, `ui/session.py` | Parcial | Fixtures cubren espacios, backslash, comillas, `$`, backticks, pérdida de foco y fallback ENTER |
| MV-PAGE-01 | `movicom` + `docs/AGENT_PROTOCOL.md` | Paginación acumulativa frente a ventana renumerada | CONTRADICTORIO | Crítica | `ui/frame.py`, `docs/AGENT_PROTOCOL.md` | Contrato inconsistente | Se elige una semántica, se documentan IDs/números válidos y existen pruebas para `more` |
| MV-SAFE-01 | `movicom` y `AGENTS.md` | Aprobación de acciones sensibles | MEJORA / NUEVO | Crítica | adapters/policies | Parcial: solo está documentado | Tools sensibles devuelven `approval_required` antes de ejecutar y no imprimen datos privados |
| BR-APP-01 | `devices/android.py` | Regex de `list_apps()` y `resolve_package()` | MEJORA / DEFECTO PROBABLE | Crítica | `devices/android.py` | Pendiente de verificar | Fixtures de `adb devices` y `query-activities` resuelven package completo, alias y varios seriales |
| BR-KNOW-01 | `knowledge/registry.py`, `ui/session.py` | `selectors.json` y `actions.json` no se ejecutan | CONTRADICTORIO | Crítica | `knowledge/`, `ui/session.py` | Inerte | Una acción de pack se compila/resuelve y devuelve `UIResult` con frame posterior |
| BR-KNOW-02 | pack MGAndroid y `tvbox-controller/ids.yaml` | IDs completos versus abreviados y `channel_name` versus `tv_live_name` | CONTRADICTORIO / NO_DECIDIBLE | Crítica | pack MGAndroid | No validado con dump real | Se define formato canónico y fixtures prueban IDs reales y alias documentados |
| BR-UI-01 | `ui/session.py` | `up/down` implementados como swipe fijo | CONTRADICTORIO | Alta | `ui/session.py`, `devices/` | Pendiente | DPAD y scroll tienen verbos distintos y viewport configurable |
| BR-ERR-01 | adapters y `ADBError` | Errores mezclan `RuntimeError`, `ValueError` y strings | MEJORA | Alta | `exceptions.py`, adapters | Parcial | MCP/REST serializan códigos estables: `device_unavailable`, `adb_timeout`, `selector_not_found`, etc. |
| BR-RT-01 | MCP runtime y `UISession` | Sin reconnect/wakeup/selección obligatoria | NUEVO | Alta | runtime/transport | Falta | Dispositivo perdido produce estado recuperable, reintento limitado y serial explícito |

## 4. Auditoría de `pyt-androidtv`

### 4.1 ADB y transporte

**Fuentes:**

- `src/pyt_androidtv/adb/base.py`
- `src/pyt_androidtv/adb/tcp.py`
- `src/pyt_androidtv/adb/server.py`

**Capacidades observadas:**

- Contrato ADB asíncrono con disponibilidad, conexión, cierre y shell.
- Conexión ADB TCP con configuración de host y puerto.
- Backend mediante servidor ADB configurable.
- Timeouts de autenticación, transporte y operación.
- Claves RSA.
- `pull`, `push` y `screencap`.
- Excepciones específicas para indisponibilidad, lock, reglas inválidas y comandos.

**Clasificación:** `NUEVO`, `MEJORA` y `VARIANTE`.

**Decisión:** extender el contrato único de `android_agent_bridge/src/android_agent_bridge/adb/transport.py`. No portar las fachadas completas ni crear un segundo cliente ADB para el adapter Home Assistant o REST.

**Faltante concreto:** el bridge no expone todavía `pull`, `push`, `screencap`, un backend ADB server, política de reconnect ni timeouts diferenciados en el contrato público.

### 4.2 Metadatos del dispositivo

**Fuentes:**

- `src/pyt_androidtv/models.py`
- `src/pyt_androidtv/basetv/base.py`
- `BaseTV.get_device_properties()`
- `BaseTV.get_screen_resolution()`
- `BaseTV.get_screen_density()`

**Capacidades:**

- Fabricante.
- Modelo.
- Serial.
- Versión Android.
- Product ID.
- MAC Wi-Fi/Ethernet.
- Resolución y densidad.

**Clasificación:** `NUEVO`.

**Decisión:** añadir un snapshot de dispositivo y capacidades de diagnóstico, separado de `Frame.screen`. El agente no debe recibir estos datos en cada frame; deben estar disponibles mediante `android_doctor` o una consulta explícita y sanitizada.

### 4.3 Estado físico y multimedia

**Fuentes:**

- `BaseTV.screen_on()`
- `BaseTV.awake()`
- `BaseTV.current_app()`
- `BaseTV.current_app_media_session_state()`
- `BaseTV.audio_state()`
- `BaseTV.wake_lock_size()`
- `BaseTV.get_hdmi_input()`
- `src/pyt_androidtv/basetv/state.py`

**Capacidades:**

- Pantalla encendida/apagada.
- Dispositivo despierto.
- Wake locks.
- App en foreground.
- Estado de sesión multimedia.
- Audio `idle`, `paused` o `playing`.
- Entrada HDMI.
- Motor configurable de reglas de estado.

**Clasificación:** `NUEVO` y `MEJORA`.

**Decisión:** crear observadores de dispositivo en `devices/` o `diagnostics/`. No mezclar el estado físico con el estado de pantalla que reconoce un knowledge pack.

### 4.4 Volumen, mute y multimedia

**Fuentes:**

- `BaseTV.stream_music_properties()`
- `BaseTV.set_volume_level()`
- `BaseTV.volume_up()`
- `BaseTV.volume_down()`
- `BaseTV.mute()`
- `BaseTV.media_play()`, `media_pause()`, `media_stop()`, `media_next()` y `media_previous()`
- `constants.py` y `CommandRegistry`

**Capacidades:**

- Lectura del volumen.
- Volumen normalizado entre `0.0` y `1.0`.
- Mute.
- Dispositivo de salida de audio.
- Play, pause, stop, next y previous.
- Mapa de teclas Android TV.

**Clasificación:** `NUEVO`.

**Decisión:** añadir capacidades tipadas y una allowlist de verbos seguros. No exponer un `keycode` arbitrario como interfaz principal para el LLM.

Verbos candidatos:

```text
left, right, enter, menu,
play, pause, stop, next, previous,
volume_up, volume_down, mute,
power, sleep
```

### 4.5 Power y tipos de dispositivo

**Fuentes:**

- `src/pyt_androidtv/androidtv/androidtv.py`
- `src/pyt_androidtv/firetv/firetv.py`
- `BaseTV.sleep()`

**Capacidades:**

- Encendido.
- Apagado.
- Suspensión.
- Estrategias específicas de Android TV y Fire TV.
- Intent de lanzamiento distinto según el tipo.

**Clasificación:** `NUEVO` y `VARIANTE`.

**Decisión:** usar estrategias o traits por tipo de dispositivo. No duplicar completamente dos clases de dispositivo dentro del bridge.

### 4.6 Discovery y pairing

**Fuentes:**

- `src/pyt_androidtv/wireless/discovery.py`
- `src/pyt_androidtv/wireless/pairing.py`

**Capacidades:**

- Scan de red.
- Zeroconf/mDNS.
- Detección de servicios ADB.
- Pairing inalámbrico con código.
- `adb tcpip` por USB.
- Conexión TCP.
- Disconnect/reconnect.
- Estado de conexión.

**Clasificación:** `NUEVO`.

**Decisión:** crear una capa de provisioning separada. El scan y el pairing requieren consentimiento explícito y no deben ejecutarse automáticamente desde una herramienta normal del agente.

**Advertencia:** un puerto TCP abierto no demuestra por sí solo que exista un servicio ADB válido. La detección debe validar el handshake.

### 4.7 Diagnóstico

**Fuentes:**

- `src/pyt_androidtv/diagnostics/system.py`
- `src/pyt_androidtv/diagnostics/network.py`
- `src/pyt_androidtv/diagnostics/apps.py`
- `src/pyt_androidtv/diagnostics/report.py`

**Capacidades:**

- Memoria.
- Storage.
- Uptime.
- Boot count.
- Servicios.
- Interfaces de red.
- DNS.
- Wi-Fi.
- Paquetes instalados.
- Procesos.
- Top memory.
- Reporte resumido o completo.

**Clasificación:** `NUEVO`.

**Decisión:** incorporar consultas bajo demanda a `diagnostics/` y ampliar `android_doctor`. Los reportes completos no deben entrar en todos los frames ni enviarse automáticamente al modelo. SSID, MAC, procesos y dumps requieren sanitización.

### 4.8 Captura, grabación y archivos

**Fuentes:**

- `ADBInterface.pull()`
- `ADBInterface.push()`
- `ADBInterface.screencap()`
- `BaseTV.screen_record()`

**Clasificación:** `NUEVO`.

**Decisión:** incorporar captura y transferencia bajo una política explícita de paths permitidos, tamaño, retención y consentimiento. La grabación es una operación larga y no debe ser una acción MCP implícita.

### 4.9 Lo exclusivo de Home Assistant

**Fuentes:**

- `custom_components/pyt_androidtv/media_player.py`
- `custom_components/pyt_androidtv/sensor.py`
- `custom_components/pyt_androidtv/camera.py`
- `custom_components/pyt_androidtv/config_flow.py`
- `custom_components/pyt_androidtv/services.yaml`
- `strings.json`
- `manifest.json`
- `docs/HOME_ASSISTANT.md`
- `mushroom_config_examples.yaml`

**Clasificación:** `FUERA_DE_ALCANCE` para el núcleo.

No portar al core:

- Entidades `media_player`, `sensor` o `camera`.
- Entity registry.
- ConfigFlow y OptionsFlow.
- Schemas de servicios Home Assistant.
- Traducciones.
- Mushroom cards.
- Polling propio de Home Assistant.

Se puede construir posteriormente un adapter Home Assistant sobre el runtime común. No se debe crear otro cliente ADB ni copiar las entidades al bridge.

### 4.10 Contratos rotos detectados en `pyt-androidtv`

La auditoría también encontró inconsistencias que impiden copiar esta integración sin corregirla:

- `adb_command` usa `device.adb_shell()`, método que no existe como API pública de `BaseTV`.
- `camera.py` llama `device.screencap()`, aunque `screencap` está en la capa ADB y no se delega claramente a `BaseTV`.
- Algunas opciones de `OptionsFlow` se almacenan pero no se aplican al entity.
- La documentación muestra constructores que no coinciden con las firmas actuales.
- `WirelessADB.get_status()` trata conexión actual como si demostrara pairing persistente.
- Algunas respuestas de shell se convierten en `None`, mientras que `pull` y `push` lanzan excepciones; el bridge debe normalizar estos errores.

## 5. Auditoría de `Flujo_android`

**Fuentes revisadas:**

- `device.py`
- `node.py`
- `ui.py`
- `selector.py`
- `app.py`
- `mgandroid.py`
- `channel_extractor.py`
- `crawler.py`
- `main.py`

### 5.1 Selector rico

**Capacidades:**

- Texto exacto.
- Texto parcial.
- Regex.
- Resource ID parcial.
- Clase.
- Content description.
- Región.
- Área.
- Jerarquía.
- Predicados.
- Orden.
- Selección entre múltiples nodos.

**Clasificación:** `MEJORA` con partes `NUEVO`.

El bridge necesita un resolvedor declarativo capaz de evaluar selectores como:

```json
{
  "resource_id": "channel_name",
  "text_contains": "ESPN",
  "parent_clickable": true
}
```

La resolución debe ocurrir contra el árbol fresco actual y producir un nodo interno, no coordenadas persistentes.

### 5.2 Lifecycle de MGAndroid

**Capacidades:**

- `open`.
- `close`.
- `restart`.
- `wait_ready`.
- `ensure_home`.
- `is_on_home`.
- Espera por varios indicadores.
- Recuperación tras una pantalla inesperada.

**Clasificación:** `NUEVO`.

`AndroidDevice.open_app()` no reemplaza este lifecycle específico. El comportamiento debe ser un workflow o policy del pack MGAndroid y validar el estado después de cada transición.

### 5.3 Funciones específicas de MGAndroid

**Capacidades:**

- Live.
- Series.
- Películas.
- Anime.
- Especiales.
- Settings.
- Historial.
- Favoritos.
- Banner.
- Player.
- Canales.
- Búsqueda.
- Estado actual.
- Screenshots.

**Clasificación:** `NUEVO` para la mayoría.

**Decisión:** migrar como actions y workflows del pack `knowledge/apps/mgandroid/`, no como una clase monolítica que duplique el núcleo.

### 5.4 Channel extractor

**Fuente:** `Flujo_android/channel_extractor.py`.

**Capacidades:**

- Apertura del panel lateral.
- Selección de categorías.
- Lectura de canales.
- Números de canal.
- EPG.
- Favoritos.
- Canal seleccionado.
- Reproducción.
- Navegación DPAD.
- Deduplicación.
- Exportación.

**Clasificación:** `NUEVO`.

Es uno de los faltantes más importantes para igualar la funcionalidad MGAndroid. El filtro legado `bounds.left > 300` no debe copiarse: debe sustituirse por jerarquía, resource ID, contenedor padre y regiones calculadas desde la pantalla actual.

### 5.5 Crawler, dumps y diagnóstico

**Fuente:** `Flujo_android/crawler.py` y `main.py`.

**Capacidades:**

- Crawl de categorías, canales e items.
- Screenshots.
- Dumps XML.
- Exportación JSON, TXT y CSV.
- Diagnóstico manual.
- CLI interactiva.

**Clasificación:** `NUEVO`, pero como herramienta de diagnóstico y construcción de packs.

No debe ejecutarse como parte del ciclo normal del agente. Sus resultados deben tratarse como evidencia candidata y validarse antes de actualizar el pack oficial.

### 5.6 DPAD frente a swipe

`UISession` usa actualmente swipe fijo para `up` y `down`. En Android TV esto no equivale al DPAD.

Decisión:

```text
up/down/left/right = KEYCODE_DPAD_*
scroll = swipe
```

El swipe debe conservarse como acción distinta, con viewport calculado, no con coordenadas fijas de 1080p.

## 6. Auditoría de `tvbox-controller`

**Fuentes revisadas:**

- `app.py`
- `actions.py`
- `config.py`
- `device.py`
- `engine.py`
- `mgandroid.py`
- `ocr.py`
- `llm_vision.py`
- `ids.yaml`
- `Dockerfile`
- `docker-compose.yml`
- `requirements.txt`
- `README.md`

### 6.1 Control MGAndroid

**Capacidades observadas:**

- Live.
- Series.
- Películas.
- Anime.
- Especial.
- Settings.
- Historial.
- Favoritos.
- Panel de canales.
- Categorías de canales.
- Canal actual.
- Velocidad.
- Selección de canal.
- Búsqueda de canales.
- Recuperación al home.
- Estado básico.
- Screenshot.

**Clasificación:** `NUEVO` y `MEJORA`.

La navegación debe migrarse al pack y a workflows, no conservar `TVDevice` con `uiautomator2` como segundo cliente de UI/ADB.

### 6.2 Panel de canales y búsqueda

Faltan en el bridge:

- Abrir panel de canales.
- Seleccionar categoría.
- Enumerar canales visibles.
- Identificar canal actual.
- Seleccionar canal por nombre.
- Buscar canal.
- Canal arriba/abajo.
- Leer velocidad o estado del reproductor.

**Clasificación:** `NUEVO`.

Cada workflow debe verificar pantalla de origen, actuar sobre un frame fresco y verificar el frame siguiente.

### 6.3 IDs de MGAndroid

`tvbox-controller/ids.yaml` contiene IDs completos como:

```text
com.android.mgandroid:id/iv_logo
```

El pack del bridge contiene formas abreviadas como:

```text
iv_logo
```

El parser conserva el resource ID tal como viene en el XML y la comparación actual puede ser exacta. Por tanto, el pack puede no reconocer dumps reales.

**Clasificación:** `CONTRADICTORIO` / `NUEVO` como corrección requerida.

**Decisión:** definir una normalización explícita en el límite del knowledge pack o almacenar IDs completos validados. No alterar globalmente el parser para ocultar diferencias de procedencia.

También debe corregirse la discrepancia entre `tv_live_name` del legado y el selector `channel_name`/equivalente usado por el pack actual, validándolo contra dumps reales.

### 6.4 Motor de decisión

**Fuente:** `engine.py`.

**Capacidades:**

- Parser de objetivos sencillos.
- Navegación por frases.
- Fallback por resource ID.
- Fallback por texto.
- OCR.
- Computer vision.
- LLM vision.

**Clasificación:** `VARIANTE`.

El bridge no necesita copiar este motor como fachada principal: su contrato es que el agente lea un frame y envíe una acción explícita. Algunas traducciones pueden reutilizarse como adapter de intención:

```text
"ir a películas" → workflow open_movies
"poner ESPN HD" → workflow select_channel
"buscar FOX" → workflow search_channel
```

### 6.5 OCR, CV y LLM Vision

**Fuentes:**

- `ocr.py`
- `vision.py` o módulo CV equivalente
- `llm_vision.py`
- `engine.py`

**Clasificación:** `NUEVO`, pero opcional y condicionado a seguridad.

El flujo actual es:

```text
captura → detecta coordenadas → tap directo
```

No debe migrarse literalmente. El flujo compatible con el bridge es:

```text
captura → proveedor OCR/CV/LLM
→ candidato temporal con confianza
→ validación contra UI fresca
→ acción interna
→ nuevo frame
```

La imagen no debe enviarse a proveedores externos sin consentimiento. El proveedor de visión no debe ejecutar shell ni poder saltarse las políticas de la sesión.

### 6.6 REST, Docker y Home Assistant/n8n

**Fuentes:**

- `app.py`
- `Dockerfile`
- `docker-compose.yml`

**Clasificación:** `VARIANTE` y parcialmente `FUERA_DE_ALCANCE`.

`tvbox-controller` declara endpoints como `/home`, `/back`, `/settings`, `/history`, `/favorites`, `/channels`, `/search`, `/key`, `/volume/up`, `/screenshot`, `/action` y `/ha/...`, pero varios llaman métodos inexistentes en `TVActions`. La API declarada no representa completamente el comportamiento real.

La migración correcta es ampliar el adapter REST del bridge sobre el runtime persistente:

```text
REST / MCP / CLI
       ↓
BridgeRuntime
       ↓
AndroidDevice + UISession + KnowledgeRegistry
       ↓
ADBTransport único
```

Problemas de despliegue y seguridad observados:

- CORS abierto a cualquier origen.
- Healthcheck que depende de `curl` sin garantía de estar instalado.
- Red Docker externa requerida.
- Ausencia de autenticación REST.
- Servidor que puede iniciar aunque el dispositivo no esté conectado.
- Acceso concurrente sin una política clara de lock.
- Dependencias OCR/CV pesadas mezcladas con el runtime base.

Docker y n8n deben ser adapters o despliegues opcionales, no parte del núcleo.

## 7. Auditoría de `movicom`

### 7.1 Herramientas genéricas del sistema

Faltan o no están implementadas en el bridge:

- App store mediante `market://`.
- App intent.
- Abrir URLs.
- Navegación web.
- Búsqueda web.
- Listar contactos.
- Buscar contactos.
- Añadir contactos.
- Listar notificaciones con filtros.
- Cámara/fotografía.
- Fallback de screenshot.
- Descarga de capturas.

**Clasificación:** `NUEVO`.

Contactos, llamadas, mensajes, instalaciones, publicaciones y acciones equivalentes requieren aprobación explícita. No deben convertirse automáticamente en herramientas sin policy.

### 7.2 Workflows ejecutables

`workflows/model.py` existe en el bridge como modelo de datos, pero todavía falta un runner que:

- Cargue workflows.
- Ejecute pasos.
- Reevalúe la pantalla entre pasos.
- Detenga la secuencia si el estado cambia.
- Mantenga una sola `UISession`.
- Requiera aprobación para operaciones sensibles.

**Clasificación:** `NUEVO`.

### 7.3 Teclado y entrada

Faltan o deben mejorar:

- Limpieza de campos.
- Detección del teclado virtual.
- Fallback con `ENTER` cuando no existe botón submit.
- Detección de botón submit.
- Escape robusto para `input text`.
- Reintentos cuando se pierde el foco.
- Reintentos ante `null-root`.
- Wakeup antes de interactuar.
- Dismiss del teclado cuando corresponda.

**Clasificación:** `MEJORA`.

El transporte debe ser el único lugar donde se defina el escaping de texto. La implementación actual del bridge transforma espacios y `%`, mientras que `pyt-androidtv` también contempla backslash, comillas, `$` y backticks.

### 7.4 Paginación

Existe una contradicción entre el contrato documental y la implementación:

- `docs/AGENT_PROTOCOL.md` describe paginación acumulativa inspirada en `movicom`, conservando números previos.
- `FrameBuilder` calcula una ventana nueva mediante `start = (page - 1) * page_size` y vuelve a numerar desde uno.

**Clasificación:** `CONTRADICTORIO`.

Antes de ampliar los workflows debe fijarse una política:

1. Paginación por ventana con renumeración.
2. Paginación acumulativa conservando acciones previas.
3. Cursor o identificador estable.

El contrato debe especificar qué acciones permanecen válidas después de `more`. Para un agente, los identificadores estables son preferibles a depender solo de una posición numérica que pueda cambiar.

### 7.5 Ranking, reintentos y aprobación

Faltan o deben mejorarse:

- Filtro de ruido de acciones.
- Ranking de acciones relevantes.
- Reintentos ante pantalla vacía.
- Wakeup y recuperación de focus.
- Aprobación formal para contactos, mensajes, llamadas, instalaciones y publicaciones.

**Clasificación:** `MEJORA` y `NUEVO`.

## 8. Defectos o riesgos propios del bridge

### 8.1 Resolución de aplicaciones

En `src/android_agent_bridge/devices/android.py`, los regex de `list_apps()` y `resolve_package()` deben revisarse cuidadosamente. Si los escapes se interpretan como barras invertidas literales, la lista puede quedar vacía y `mgandroid` no podrá resolverse.

**Clasificación:** defecto probable `P0`.

Debe validarse con salidas reales o fixtures de:

```text
adb devices
adb shell cmd package query-activities ...
```

### 8.2 Knowledge pack inerte

Actualmente:

- `manifest.json` participa.
- `states.json` participa parcialmente.
- `selectors.json` no se usa para resolver acciones declarativas.
- `actions.json` no se ejecuta desde `UISession`.

**Clasificación:** `P0`.

### 8.3 Navegación incorrecta para Android TV

`UISession` usa swipe fijo para `up` y `down`. Debe diferenciarse:

```text
up/down/left/right = DPAD
scroll = swipe
```

### 8.4 Errores sin contrato uniforme

Actualmente se mezclan `ADBError`, `RuntimeError`, `ValueError` y errores genéricos serializados por los adapters. El agente necesita distinguir al menos:

```text
device_unavailable
adb_timeout
app_not_found
screen_not_recognized
selector_not_found
action_not_allowed
input_failed
verification_failed
```

### 8.5 Reconexión incompleta

El MCP mantiene una sesión persistente, pero faltan:

- Detección de dispositivo perdido.
- Reconnect controlado.
- Wakeup.
- Reintentos limitados.
- Selección obligatoria cuando existen varios seriales.
- Estado de sesión después de reconectar.

## 9. Qué no debe portarse

No debe portarse directamente al núcleo:

- Entidades y servicios de Home Assistant.
- Mushroom cards.
- ConfigFlow y entity registry.
- Docker Compose específico de `tvbox-controller`.
- CORS abierto o endpoints sin autenticación.
- Un segundo cliente `uiautomator2`.
- Shell ADB arbitrario para el LLM.
- Taps por coordenadas persistentes.
- El motor OCR/CV/LLM que actúa sin verificación.
- Filtros fijos como `bounds.left > 300`.
- Macros basadas únicamente en `sleep()` y keycodes fijos.
- Firmware, secretos, configuración de producto o documentación específica de un entorno.

Estas piezas pueden inspirar adapters o tests, pero no deben duplicar la arquitectura del bridge.

## 10. Faltantes priorizados

### P0 — Corrección del núcleo y conocimiento

1. Corregir y probar `list_apps()` y `resolve_package()`.
2. Normalizar IDs completos y abreviados del pack MGAndroid.
3. Implementar el selector declarativo de `selectors.json`.
4. Ejecutar `actions.json` desde la sesión persistente.
5. Añadir `text_contains`, resource ID parcial, content description, clase, regex, jerarquía y padre clickeable.
6. Resolver la discrepancia de `channel_name`/`tv_live_name` con evidencia XML.
7. Corregir la contradicción de paginación y actualizar la documentación.
8. Añadir fixtures y pruebas para parser, frame, selector, estado y acción MGAndroid.

### P1 — MGAndroid y Android TV

1. Lifecycle MGAndroid: `wait_ready`, `ensure_home`, `restart` y `close`.
2. Workflows de live, movies, series, anime, settings, favorites e history.
3. Panel de canales, categorías, selección por nombre y búsqueda.
4. DPAD completo y separación explícita de scroll.
5. Snapshot de dispositivo con modelo, Android version, display, power, foreground y media state.
6. Volumen, mute, multimedia y power.
7. `screencap`, `pull` y `push` controlados.
8. Reconnect y errores estructurados.
9. REST seguro sobre el runtime persistente.

### P2 — Extensiones y adapters

1. Discovery y pairing.
2. Diagnóstico completo.
3. OCR/CV como proveedores opcionales.
4. LLM Vision con consentimiento, confianza y verificación.
5. Workflows genéricos de `movicom`.
6. Contacts, notifications, web, intents y cámara.
7. Adapter Home Assistant.
8. Docker y n8n como despliegues/adapters.

## 10.1 Backlog de implementación verificable

Las prioridades anteriores se convierten aquí en tareas ejecutables. Cada tarea tiene una sola salida principal, dependencias explícitas y una condición de cierre verificable. Los estados se actualizan conforme a la implementación; una tarea parcial permanece `EN_PROGRESO`.

### Incremento implementado en esta rama

El primer incremento ya implementa parcialmente los P0 y permanece deliberadamente acotado:

- corrección de los regex y validación contra aplicaciones launchable en `AndroidDevice`;
- `SelectorResolver` determinista con IDs completos/sufijos, texto, `text_contains`, regex, content description, clase, región y padre clickeable;
- validación tipada de `actions.json` con allowlist de intents y rechazo de campos arbitrarios;
- ejecución de acciones declarativas `navigate` y `select_by_name` mediante `UISession` y dump fresco;
- acciones de knowledge pack visibles como verbos estables en el frame;
- el compilador expande referencias nombradas de `selectors.json` como `home.category` y `live.channel`;
- `UIResult` serializa códigos estables como `action_not_found`, `input_required`, `pagination_end` y `action_failed`;
- DPAD separado de `scroll` con viewport efímero;
- paginación acumulativa con posición estable de `more`;
- nueve pruebas sin dispositivo mediante `FakeADBTransport` y el fixture `examples/mgandroid_live.xml`.

Este segundo incremento no completa todavía AB-P0-01, AB-P0-07 ni AB-P0-09: faltan fixtures adicionales de input/panel, validación con dumps reales, corrección definitiva de nombres MGAndroid y el gate completo de regresión. Por eso esos estados se mantienen `EN_PROGRESO` o `PENDIENTE`.

### Secuencia de ejecución

```text
AB-P0-01 fixtures y fake transport
        ↓
AB-P0-02 regex de apps ───────────────┐
AB-P0-03 contrato de IDs ──────────────┤
        ↓                             │
AB-P0-04 selector engine ─────────────┤
        ↓                             │
AB-P0-05 compilador de actions ───────┤
        ↓                             │
AB-P0-06 executor read-act-read ──────┤
        ↓                             │
AB-P0-07 pack MGAndroid canónico ─────┤
        ↓                             │
AB-P0-08 paginación + DPAD ───────────┘
        ↓
AB-P0-09 gate de pruebas P0
        ↓
AB-P1-01..AB-P1-08 capacidades TV, workflows y REST seguro
        ↓
AB-P2-01..AB-P2-08 discovery, diagnóstico, percepción y adapters
```

### Tareas P0 — núcleo y conocimiento

| ID | Tarea | Fuentes de procedencia | Archivos objetivo | Dependencias | Validación / definición de terminado | Estado |
|---|---|---|---|---|---|---|
| AB-P0-01 | Crear fixtures sanitizados y `FakeADBTransport` | `examples/mgandroid_home.xml`, dumps de `Flujo_android`, tests de `pyt-androidtv` | `tests/`, `examples/`, posible `tests/fakes.py` | Ninguna | Fixtures cubren home, live, panel de canales, input y pantalla desconocida; todas las pruebas pueden ejecutarse sin dispositivo | EN_PROGRESO |
| AB-P0-02 | Corregir resolución de apps y validación de package | `AndroidDevice.list_apps()`, `resolve_package()`, salida ADB de `tvbox-controller` | `devices/android.py`, `tests/test_devices.py` | AB-P0-01 | Alias `mgandroid`, package completo y lista de launchables funcionan con fixtures; package inválido se rechaza | COMPLETADA |
| AB-P0-03 | Definir normalización canónica de resource IDs | `tvbox-controller/ids.yaml`, XML de `Flujo_android`, pack actual | `knowledge/registry.py`, pack MGAndroid, `tests/test_knowledge.py` | AB-P0-01 | Se decide si el pack guarda IDs completos o sufijos; se prueban ambos solo mediante una función explícita y documentada | COMPLETADA |
| AB-P0-04 | Implementar selector declarativo ordenado | `Flujo_android/selector.py`, `selectors.json` | `ui/selectors.py`, `knowledge/registry.py`, tests | AB-P0-03 | Soporta ID exacto/parcial, texto exacto/contiene, regex, content-desc, clase, región, jerarquía y padre clickeable; devuelve nodo o error estable | EN_PROGRESO |
| AB-P0-05 | Compilar acciones del knowledge pack | `actions.json`, `tvbox-controller/actions.py` | `knowledge/`, `workflows/model.py`, tests | AB-P0-04 | `actions.json` se valida, tiene schema estable, resuelve selector y no permite shell/coordenadas persistentes | COMPLETADA |
| AB-P0-06 | Conectar actions con `UISession` | `UISession.do()`, contrato `read → do → read` | `ui/session.py`, `ui/frame.py`, tests | AB-P0-05 | Una acción declarativa se ejecuta contra dump fresco, devuelve `UIResult` y frame posterior; fallos no dejan estado ambiguo | COMPLETADA |
| AB-P0-07 | Consolidar pack MGAndroid y corregir nombres | `Flujo_android/mgandroid.py`, `tvbox-controller/ids.yaml`, pack actual | `knowledge/apps/mgandroid/*.json`, fixtures y docs | AB-P0-03, AB-P0-06 | Manifest, estados, selectores y acciones solo declaran capacidades respaldadas; `channel_name`/`tv_live_name` queda resuelto con evidencia | PENDIENTE |
| AB-P0-08 | Resolver contrato de paginación y navegación TV | `movicom`, `docs/AGENT_PROTOCOL.md`, `UISession` | `ui/frame.py`, `ui/session.py`, `docs/AGENT_PROTOCOL.md`, tests | AB-P0-01 | `more` tiene semántica única; números/IDs válidos están documentados; DPAD no usa swipe fijo y `scroll` es separado | COMPLETADA |
| AB-P0-09 | Crear gate de regresión del núcleo | CI de `pyt-androidtv`, ejemplos del bridge | `tests/`, workflow CI si existe | AB-P0-02..AB-P0-08 | Parser, selector, frame, pack, executor, paginación, DPAD y errores pasan con `compileall`, Ruff y tests reproducibles | PENDIENTE |

### Tareas P1 — MGAndroid y Android TV

| ID | Tarea | Fuentes de procedencia | Archivos objetivo | Dependencias | Validación / definición de terminado | Estado |
|---|---|---|---|---|---|---|
| AB-P1-01 | Implementar lifecycle MGAndroid | `Flujo_android/app.py`, `Flujo_android/mgandroid.py`, `tvbox-controller/mgandroid.py` | `workflows/`, pack MGAndroid, `ui/session.py` | AB-P0-07 | `wait_ready`, `ensure_home`, `restart` y `close` tienen timeout, estado de origen, recovery limitado y frame de salida | PENDIENTE |
| AB-P1-02 | Implementar navegación de categorías y estado MGAndroid | `Flujo_android/mgandroid.py`, `tvbox-controller/mgandroid.py` | workflows y pack | AB-P1-01 | Live, movies, series, anime, special, settings, history y favorites se ejecutan con selectores; cada transición se verifica | PENDIENTE |
| AB-P1-03 | Implementar panel y búsqueda de canales | `channel_extractor.py`, `tvbox-controller/mgandroid.py` | pack, workflows, fixtures | AB-P0-07, AB-P0-08 | Panel, categorías, lista, canal actual, selección por nombre, búsqueda y up/down funcionan sin `left > 300` fijo | PENDIENTE |
| AB-P1-04 | Añadir snapshot de dispositivo y estado TV | `pyt-androidtv/models.py`, `BaseTV`, `basetv/state.py` | `devices/`, `diagnostics/`, exceptions, tests | AB-P0-09 | Doctor distingue metadata, power, foreground y media state; no incluye PII por defecto ni altera frames | PENDIENTE |
| AB-P1-05 | Añadir volumen, media, power y key allowlist | `pyt-androidtv/constants.py`, `BaseTV`, `AndroidTV`, `FireTV` | `adb/transport.py`, `devices/`, adapters, tests | AB-P1-04 | Verbos semánticos generan comandos correctos, validan dispositivo y rechazan keycodes arbitrarios | PENDIENTE |
| AB-P1-06 | Añadir captura, transferencia y operación larga controlada | `pyt-androidtv/adb/*`, `BaseTV.screen_record()`, `tvbox-controller/device.py` | `adb/transport.py`, `diagnostics/`, adapters | AB-P0-09 | `screencap`, `pull`, `push` y grabación tienen allowlist de paths, límites y cleanup; no exponen imagen automáticamente al LLM | PENDIENTE |
| AB-P1-07 | Normalizar errores, reconnect y wakeup | excepciones de `pyt-androidtv`, runtime MCP, `movicom` retries | `exceptions.py`, runtime MCP/REST, transport, tests | AB-P1-04 | Errores serializan códigos estables; dispositivo perdido se recupera con retry limitado y serial explícito | PENDIENTE |
| AB-P1-08 | Endurecer REST y exponer capacidades mínimas | `tvbox-controller/app.py`, REST actual del bridge | `adapters/rest.py`, configuración y docs | AB-P1-07 | REST tiene auth o límite de red documentado, CORS allowlist, lock, health real, validación y errores HTTP estructurados | PENDIENTE |

### Tareas P2 — extensiones y adapters separados

| ID | Tarea | Fuentes de procedencia | Archivos objetivo | Dependencias | Validación / definición de terminado | Estado |
|---|---|---|---|---|---|---|
| AB-P2-01 | Implementar discovery y pairing como provisioning explícito | `pyt-androidtv/wireless/*` | `provisioning/`, adapters, docs | AB-P1-07 | Scan valida handshake; pairing exige aprobación, no imprime secretos y distingue paired/connected | PENDIENTE |
| AB-P2-02 | Implementar diagnóstico modular completo | `pyt-androidtv/diagnostics/*` | `diagnostics/`, `android_doctor`, tests | AB-P1-04 | Quick/full report separados, redacción de PII, límites de respuesta y ejecución bajo demanda | PENDIENTE |
| AB-P2-03 | Añadir providers OCR/CV opt-in | `tvbox-controller/ocr.py`, `vision.py`, `engine.py` | `providers/vision/`, executor, extras | AB-P1-06 | Provider devuelve candidato y confianza; executor valida frame fresco, transición y umbral | PENDIENTE |
| AB-P2-04 | Añadir LLM Vision con consentimiento | `tvbox-controller/llm_vision.py`, policies de `AGENTS.md` | adapter/provider y configuración | AB-P2-03 | Imagen no sale sin aprobación; respuesta no ejecuta shell; se registra solo evidencia no sensible | PENDIENTE |
| AB-P2-05 | Implementar system lane de `movicom` | tools system de `movicom` | adapters/system, policies, schemas | AB-P1-07 | App, intent, web, notifications, contacts y camera tienen schemas, allowlists, errores y aprobación sensible | PENDIENTE |
| AB-P2-06 | Implementar runner de workflows genéricos | workflow model de `movicom`, `workflows/model.py` | `workflows/runner.py`, schemas, tests | AB-P0-06, AB-P1-07 | Cada step reevalúa pantalla, no persiste coordenadas, soporta cancelación y devuelve evidencia estructurada | PENDIENTE |
| AB-P2-07 | Crear adapter Home Assistant sobre runtime común | `pyt-androidtv/custom_components/*` | adapter separado, docs | AB-P1-08 | HA no crea ADB secundario, traduce capacidades del bridge y conserva aprobación/seguridad | PENDIENTE |
| AB-P2-08 | Crear despliegue Docker/n8n opcional | `tvbox-controller/Dockerfile`, compose y REST | `deploy/`, docs, CI | AB-P1-08 | Healthcheck válido, red parametrizada, auth documentada y dependencias opcionales separadas del core | PENDIENTE |

### Reglas de ejecución del backlog

1. No empezar P1/P2 mientras `AB-P0-09` no pase.
2. Cada tarea debe conservar la procedencia en código o documentación y actualizar esta matriz cuando cambie el estado.
3. Una tarea se marca terminada solo si cumple su criterio de aceptación y tiene validación reproducible; una implementación parcial permanece `EN_PROGRESO`.
4. Si una fuente contradice el contrato del bridge, se conserva como evidencia de procedencia, no como comportamiento canónico.
5. Los cambios de core deben pasar por `docs/ARCHITECTURE.md`, `docs/AGENT_PROTOCOL.md` y, cuando afecten MCP, `docs/MCP.md`.
6. No copiar `custom_components`, `TVDevice`, `MGAndroidController` ni motores de visión como bloques monolíticos; extraer contratos y adapters por responsabilidad.
7. Antes de migrar datos MGAndroid desde un dump real, sanitizar textos, cuentas, tokens, screenshots y cualquier PII.

## 11. Decisión final de arquitectura

La fusión de los cuatro proyectos es viable, pero por capas:

```text
ADBTransport
    ↓
AndroidDevice + capabilities
    ↓
UI parser + selector resolver
    ↓
UISession / Frame / workflows
    ↓
Knowledge packs, especialmente MGAndroid
    ↓
MCP / REST / CLI / Home Assistant adapters
```

El primer hito técnico debe ser hacer ejecutable y testeable el pack MGAndroid. El segundo debe incorporar las capacidades de TV de `pyt-androidtv` sin degradar el protocolo agent-first. Después se pueden añadir las herramientas genéricas de `movicom` y los adapters REST, Home Assistant, Docker y n8n.

La auditoría concluye que `custom_components` de `pyt-androidtv` no representa todo el valor de ese repositorio: es solo la capa Home Assistant. La contribución reutilizable principal está en ADB, estado, multimedia, power, diagnóstico, wireless y transferencia. Del mismo modo, `tvbox-controller` aporta ideas y evidencia de comportamiento MGAndroid, pero su API actual contiene rutas declaradas que no deben tomarse como capacidades ya verificadas.
