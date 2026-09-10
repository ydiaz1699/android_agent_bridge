# MCP para el LLM

`android-agent-mcp` es un adaptador MCP opcional. No contiene un modelo: expone el bridge para que Claude Desktop, Kiro, otro cliente MCP o un agente propio pueda pedir observaciones y acciones.

```text
LLM / cliente MCP
       ↓ stdio MCP
android-agent-mcp
       ↓ una UISession persistente
android_agent_bridge
       ↓ ADB
Android / Android TV / emulador
```

## Por qué no es un wrapper de `movicom.js`

El servidor MCP mantiene un único `SubprocessADB`, `AndroidDevice`, `KnowledgeRegistry` y `UISession` durante toda la ejecución. Así conserva la página de acciones y resuelve cada acción sobre un dump fresco. Lanzar un proceso nuevo por cada tool call perdería ese estado y podría hacer que un número visible en un frame apunte a otra acción.

## Instalación desde el checkout

Con `uv`:

```bash
uv sync --extra mcp
```

Con `pip`:

```bash
pip install -e '.[mcp]'
```

Requisitos operativos:

- Node.js no es necesario para el bridge;
- `adb` debe estar en `PATH`;
- el dispositivo debe aparecer como `device` en `adb devices`;
- el pack de conocimiento debe ser accesible por `ANDROID_AGENT_KNOWLEDGE_ROOT` cuando el servidor se inicia desde otro directorio.

## Ejecución

```bash
ANDROID_AGENT_SERIAL=192.168.1.50:5555 \
ANDROID_AGENT_KNOWLEDGE_ROOT=/ruta/android_agent_bridge/knowledge/apps \
android-agent-mcp
```

También se puede pasar la configuración como argumentos:

```bash
android-agent-mcp \
  --serial 192.168.1.50:5555 \
  --knowledge-root /ruta/android_agent_bridge/knowledge/apps
```

El transporte es `stdio`; no se debe escribir logging normal a stdout porque ese canal pertenece al protocolo MCP.

## Configuración de un cliente MCP

Ejemplo conceptual para un cliente que pueda ejecutar `uv`:

```json
{
  "mcpServers": {
    "android-agent-bridge": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "C:\\Users\\Alex\\src\\android_agent_bridge",
        "android-agent-mcp"
      ],
      "env": {
        "ANDROID_AGENT_SERIAL": "192.168.1.50:5555",
        "ANDROID_AGENT_KNOWLEDGE_ROOT": "C:\\Users\\Alex\\src\\android_agent_bridge\\knowledge\\apps"
      }
    }
  }
}
```

En Linux/macOS se sustituyen las rutas por rutas absolutas del checkout. No se deben introducir secretos en esta configuración.

## Tools expuestas

| Tool | Función |
|---|---|
| `android_doctor` | Lista dispositivos ADB y app en foreground. |
| `android_app_list` | Lista aplicaciones launchables. |
| `android_app_open` | Abre una app por alias o package; `fresh=true` fuerza inicio limpio. |
| `android_ui_frame` | Devuelve el frame compacto `app`, `screen`, `read` y `do`. |
| `android_ui_do` | Ejecuta una acción numérica o un verbo estable y devuelve el siguiente frame. |
| `android_knowledge_resolve` | Devuelve el resumen de un knowledge pack sin volcar sus archivos completos. |

Flujo recomendado:

```text
android_doctor
→ android_app_open(name="mgandroid", fresh=true)
→ android_ui_frame
→ android_ui_do(action="1")
→ android_ui_do(action="open", text=... solo si corresponde)
```

`android_ui_do` admite números de frame y verbos como `back`, `home`, `up`, `down`, `more` y `type`. Las coordenadas y el XML no se envían al LLM.

## Seguridad y límites

El servidor no expone una tool de shell ADB arbitrario. Las operaciones están limitadas a las capacidades declaradas por el bridge.

Las futuras tools que envíen mensajes, hagan llamadas, instalen apps, borren datos o publiquen contenido deben tener una política de aprobación explícita. No se debe interpretar una respuesta del LLM como autorización automática para una acción externa sensible.

El frame actual es efímero. Los knowledge packs son declarativos y no deben contener contraseñas, tokens, contactos reales, mensajes privados ni capturas de usuarios.

## Estado de la integración

Esta primera integración MCP cubre el ciclo agent-first básico. Contactos, notificaciones, intents, cámara, OCR, visión y workflows ejecutables se añadirán sobre el mismo runtime; no deben implementarse como un segundo cliente ADB.
