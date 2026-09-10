# Instrucciones para agentes

`android_agent_bridge` es un bridge agent-first para controlar Android mediante ADB. El agente decide **qué** quiere hacer; el bridge resuelve **cómo** localizarlo y ejecutarlo. El núcleo no debe quedar acoplado a una aplicación concreta.

## Regla principal

Usa el frame actual como interfaz de la pantalla. No razones sobre coordenadas ni sobre el XML crudo salvo que estés ejecutando un diagnóstico explícito.

```text
android_doctor
→ android_app_open(name="...", fresh=true)
→ android_ui_frame
→ android_ui_do(action="<número o verbo>")
→ leer el siguiente frame
```

Cada `android_ui_do` debe ejecutarse contra una pantalla fresca y devolver el siguiente frame. No reutilices coordenadas, nodos o números de una pantalla anterior.

## Capas del proyecto

- `adb/`: único transporte ADB. No crees otro cliente ADB en un adapter.
- `devices/`: capacidades generales de teléfono, emulador, Android TV y Fire TV.
- `ui/`: parser XML, árbol de nodos, resolución del padre clickeable, frames y sesión.
- `knowledge/`: carga de knowledge packs por package o alias.
- `knowledge/apps/<app>/`: conocimiento declarativo de cada aplicación.
- `workflows/`: macros parametrizadas sin coordenadas.
- `adapters/`: CLI, REST y MCP sobre el mismo núcleo.
- `docs/`: arquitectura, protocolo y operación.

Si una aplicación nueva necesita soporte, añade un knowledge pack. No agregues sus IDs, textos o pantallas al parser global.

## Knowledge packs

El conocimiento de una aplicación se carga bajo demanda y debe permanecer separado del estado de la sesión.

Un pack puede contener:

- identidad, package names, aliases y capacidades;
- selectores ordenados por prioridad;
- indicadores de estados de pantalla;
- acciones semánticas y estrategias de fallback;
- workflows validados y sin datos sensibles;
- fixtures o evidencia sanitizada.

El pack inicial es `knowledge/apps/mgandroid/`. No guardes allí contraseñas, tokens, contactos, mensajes, capturas privadas ni coordenadas de una sesión.

## Contrato del frame

El agente recibe una representación compacta:

```json
{
  "app": "mgandroid",
  "screen": "home",
  "read": ["VIVO", "PELÍCULA"],
  "do": ["1 open: VIVO", "2 open: PELÍCULA", "3 back", "4 home"],
  "pick": "act with: ui do <n>"
}
```

- `read` contiene contenido visible.
- `do` contiene acciones disponibles.
- Un número solo tiene significado para el frame que lo mostró.
- Los verbos (`back`, `home`, `up`, `down`, `more`, `type`) son preferibles en workflows porque se vuelven a resolver sobre la pantalla actual.
- `more` pagina acciones; no debe cambiar el significado de los números ya mostrados.

No envíes al LLM por defecto:

- bounds o coordenadas;
- XML completo;
- todos los selectores del pack;
- historial completo de dumps;
- secretos o datos de cuentas.

## MCP

El servidor MCP es un adaptador, no el núcleo ni el LLM. Mantiene una sesión persistente con un transporte ADB, un `AndroidDevice`, un `KnowledgeRegistry` y una `UISession`.

Tools actuales:

- `android_doctor`: dispositivos ADB y app en foreground.
- `android_app_list`: aplicaciones launchables.
- `android_app_open`: abrir por alias o package; `fresh=true` inicia desde un punto limpio.
- `android_ui_frame`: leer el frame actual.
- `android_ui_do`: ejecutar una acción y devolver el siguiente frame.
- `android_knowledge_resolve`: obtener solo el resumen de un pack.

No agregues una tool de shell ADB arbitrario al uso normal del LLM. Las tools que envíen mensajes, llamen, instalen, borren o publiquen deben tener aprobación explícita.

El transporte MCP usa `stdio`: nunca escribas logs normales a stdout. Usa stderr para diagnóstico.

## Seguridad y datos

- Usa un serial explícito cuando haya más de un dispositivo.
- No imprimas secretos ni los incluyas en frames, packs, logs o commits.
- Trata llamadas, mensajes, instalaciones, borrados y publicaciones como acciones sensibles.
- No asumas que una intención del LLM equivale a autorización para una acción externa.
- Conserva el principio de mínimo privilegio: solo expón las operaciones necesarias.

## Cambios y validación

Antes de modificar el núcleo, revisa `docs/ARCHITECTURE.md`, `docs/AGENT_PROTOCOL.md` y, si aplica, `docs/MCP.md`.

Para validar cambios Python:

```bash
uv run --python 3.11 --no-project python -m compileall -q src
uvx ruff check src
```

Para probar el frame sin un dispositivo:

```bash
PYTHONPATH=src uv run --python 3.11 --no-project \
  python -m android_agent_bridge.adapters.cli \
  frame --xml examples/mgandroid_home.xml \
  --package com.android.mgandroid
```

No copies archivos de `movicom`, `pyt-androidtv`, `Flujo_android` o `tvbox-controller` sin adaptar su responsabilidad al diseño por capas. Extrae patrones generalizables y conserva la procedencia en la documentación cuando sea relevante.
