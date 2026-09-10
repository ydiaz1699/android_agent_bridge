# Arquitectura

## Principio

El sistema se divide por responsabilidad. Una aplicación concreta aporta conocimiento; no redefine el transporte, el parser ni el protocolo del agente.

```text
adapters (CLI/REST/Home Assistant)
            ↓
agent protocol (Frame + Action)
            ↓
UI session / executor
            ↓
UI parser + selector resolver
            ↓
ADB transport
            ↓
Android device

knowledge registry ──→ app matcher/selectors/actions
```

## Capas

### 1. `adb`

Define el contrato mínimo para ejecutar comandos y obtener un dump UI. `SubprocessADB` es la implementación local que llama a `adb`; un transporte alternativo puede implementarse sin tocar las capas superiores.

### 2. `devices`

Representa capacidades generales del dispositivo: package en foreground y captura del árbol UI. No contiene nombres de pantallas de MGAndroid.

### 3. `ui`

Parsea XML, conserva la relación padre/hijo y resuelve el target clickeable. Construye frames para el agente. El frame contiene labels y acciones, no coordenadas; el ejecutor mantiene bounds solo en memoria.

### 4. `knowledge`

Busca un pack por package, alias o identificador. La carga es bajo demanda. Un pack contiene datos declarativos:

- `manifest.json`: identidad y capacidades;
- `selectors.json`: estrategias de localización ordenadas por prioridad;
- `states.json`: indicadores de pantallas;
- `actions.json`: intenciones de alto nivel y sus estrategias.

El registry no ejecuta comandos arbitrarios desde el pack.

### 5. `workflows`

Representa macros parametrizadas. Los workflows deben comenzar desde un estado seguro y usar acciones semánticas o verbos que se vuelvan a resolver contra la pantalla actual. No se guardan coordenadas.

### 6. `adapters`

Expone el mismo núcleo como CLI, REST o integración de automatización. Los adaptadores no pueden implementar un segundo parser o un segundo cliente ADB.

## Política de memoria para el LLM

Persistente:

- identidad de la app;
- selectores y estados validados;
- capacidades;
- workflows sin datos sensibles;
- confianza y versión del pack.

Efímero:

- XML actual;
- nodos y bounds;
- frame actual;
- coordenadas;
- página de acciones;
- contenido de la pantalla.

No persistir por defecto:

- contraseñas, tokens y contactos;
- mensajes privados;
- capturas con información sensible;
- dumps de usuarios fuera de una sesión de diagnóstico explícita.

## Orden de resolución

1. selector del knowledge pack por resource-id;
2. content-desc;
3. texto exacto;
4. texto parcial;
5. estructura del árbol;
6. OCR/visión como extensiones opcionales.

La respuesta normal debe ser determinista y no depender de un LLM de visión.

## Reglas de evolución

- Un nuevo dispositivo implementa `ADBTransport`, no copia `Device`.
- Una nueva aplicación añade un pack, no modifica `FrameBuilder`.
- Una nueva interfaz añade un adapter, no duplica la sesión UI.
- Las observaciones del crawler se guardan como evidencia candidata y requieren validación antes de actualizar un pack oficial.
