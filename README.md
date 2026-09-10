# android_agent_bridge

Puente agent-first para controlar dispositivos Android mediante ADB sin acoplar el núcleo a una aplicación concreta.

## Objetivo

`android_agent_bridge` combina cuatro ideas complementarias:

- **Protocolo agent-first:** frames compactos (`read` + `do`) y acciones que devuelven el siguiente frame.
- **Transporte ADB:** una capa única para teléfonos, emuladores, Android TV y Fire TV.
- **Percepción UI:** parseo de `uiautomator dump`, árbol de nodos, selectores y resolución del padre clickeable.
- **Knowledge packs:** conocimiento específico de una aplicación cargado bajo demanda; MGAndroid es el primer pack.

La aplicación concreta no se convierte en lógica rígida del núcleo. El bridge detecta la app, carga su pack de conocimiento y aplica sus selectores, estados y acciones sobre el frame actual.

## Flujo

```text
LLM → frame JSON → ui do → selector interno → ADB → nuevo frame
                         ↑
                  knowledge pack opcional
```

El LLM no recibe XML crudo ni coordenadas. Las coordenadas solo existen dentro de la sesión de ejecución y se calculan de nuevo para cada acción.

## Estado actual

Esta primera base implementa:

- transporte ADB por subprocess, con soporte para un serial concreto;
- parseo estructural de XML de `uiautomator`;
- herencia de bounds desde ancestros clickeables;
- generación de frames JSON compactos con paginación;
- resolución de la aplicación por package o alias;
- carga bajo demanda de packs JSON;
- pack inicial de MGAndroid;
- workflows como modelo de datos y punto de extensión;
- CLI para generar frames desde un XML local o desde un dispositivo ADB.

Las integraciones REST, Home Assistant, OCR y visión se incorporarán sobre estas interfaces, no como segundos ejecutores.

## Uso rápido

```bash
python -m android_agent_bridge.adapters.cli doctor
python -m android_agent_bridge.adapters.cli frame --xml path/to/window_dump.xml
python -m android_agent_bridge.adapters.cli knowledge resolve com.android.mgandroid
```

Para usar el paquete directamente desde el checkout:

```bash
PYTHONPATH=src python -m android_agent_bridge.adapters.cli --help
```

## Desarrollo

```bash
python -m compileall -q src
PYTHONPATH=src python -m android_agent_bridge.adapters.cli --help
```

Consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) y [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) antes de añadir una nueva capa o integración.

## Procedencia conceptual

Este proyecto generaliza patrones observados en `movicom`, `pyt-androidtv`, `Flujo_android` y `tvbox-controller`. No copia su firmware, secretos ni lógica específica fuera de los knowledge packs correspondientes.
