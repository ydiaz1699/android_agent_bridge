# Contrato agent-first

## Frame

El bridge presenta la pantalla como una interfaz compacta para el agente:

```json
{
  "app": "mgandroid",
  "screen": "home",
  "read": ["VIVO", "PELÍCULA", "SERIE"],
  "do": [
    "1 open: VIVO",
    "2 open: PELÍCULA",
    "3 open: SERIE",
    "4 back",
    "5 home"
  ],
  "page": "1/1",
  "pick": "act with: ui do <n>"
}
```

`read` es contenido visible. `do` son acciones accionables. El bridge puede incluir `screen` cuando un knowledge pack reconoce el estado; si no, usa `unknown`.

## Acciones

- **Numérica:** `ui do 2`; válida solo para el frame leído inmediatamente antes.
- **Verbo:** `ui do back`, `ui do down`, `ui do type "texto"`; se vuelve a resolver contra la pantalla viva y es la forma recomendada para workflows.
- **Paginación:** `ui do more`; revela acciones adicionales sin cambiar el significado de las ya mostradas. La implementación mantiene las acciones de páginas anteriores con sus números y conserva `more` en una posición estable; las acciones nuevas se añaden después.
- **Navegación TV:** `up`, `down`, `left` y `right` son eventos DPAD. `scroll_up` y `scroll_down` son swipes separados sobre el viewport detectado.

Cada acción debe producir una nueva lectura o un error estructurado:

```json
{"did":"opened PELÍCULA","frame":{...}}
```

```json
{"error":"no action #9","error_code":"action_not_found","frame":{...}}
```

Los errores de sesión usan códigos estables, entre ellos `action_not_found`, `input_required`, `pagination_end`, `state_mismatch`, `selector_not_found` y `action_failed`.

## Seguridad del contexto

No enviar al LLM:

- coordenadas salvo modo de diagnóstico explícito;
- XML completo salvo modo de diagnóstico explícito;
- variables de entorno o secretos;
- dumps persistentes de cuentas reales.

## Ciclo recomendado

```text
1. doctor
2. identificar dispositivo y app foreground
3. cargar solo el knowledge pack coincidente
4. frame
5. seleccionar una acción
6. ejecutar contra un dump fresco
7. devolver el siguiente frame
8. registrar solo resultado y evidencia no sensible
```

El agente no debe asumir que un número conserva significado entre pantallas. El ejecutor debe reconstruir el frame antes de ejecutar una acción numérica y preservar la página actual cuando corresponda.
