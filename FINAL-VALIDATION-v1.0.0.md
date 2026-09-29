# Validación final — Codex Usage Monitor 1.0.0

Fecha: 2026-09-29  
Plataforma de build y validación local: Windows 11 x64

## Resultado

Codex Usage Monitor 1.0.0 queda preparado como release final local. No se ha
publicado ningún repositorio, release, enlace ni binario.

La base fue una copia independiente de `Codex-Usage-Monitor-v1.0.0-rc1`. Antes
de modificar el versionado se registraron hashes de los módulos funcionales en
`RC1-FUNCTIONAL-HASHES.sha256`.

## Comparación RC1 → FINAL

Cambios de runtime permitidos y verificados:

- `src/main.py`: únicamente `1.0.0-rc1` → `1.0.0` en la versión Qt.
- `src/codex_client.py`: únicamente `1.0.0-rc1` → `1.0.0` en
  `clientInfo.version`.

Los siguientes módulos son idénticos byte a byte a RC1:

- `app_paths.py`
- `codex_locator.py`
- `usage_model.py`
- `settings.py`
- `widget.py`
- `windows_topmost.py`
- `windows_autostart.py`
- `window_geometry.py`

El resto de cambios se limita a metadata y packaging (`version_info.txt`,
Inno Setup y scripts de build), contratos de versión/instalador y prueba de
upgrade, LICENSE, README, captura, release notes, changelog y este informe.
Se retiró de la copia final el informe específico de validación RC1.

El identificador de instancia única
`CodexUsageMonitor-OpenAI-unofficial-v090` se mantuvo deliberadamente para
conservar la interoperabilidad entre instalaciones durante el upgrade. No es
una versión pública ni metadata del producto.

No se detectaron cambios funcionales inesperados.

## Versiones y metadata

- Python: `3.14.3`
- PySide6: `6.11.2`
- PyInstaller: `6.22.3`
- Inno Setup: `7.1.0`
- ProductVersion: `1.0.0`
- FileVersion: `1.0.0.0`
- AppId: `{5C6581F9-7DA6-4269-B760-9FE3799FABB7}` (sin cambios)
- Nombre público: `Codex Usage Monitor`
- Ejecutable: `CodexUsageMonitor.exe`
- Firma Authenticode del EXE y Setup: `NotSigned`

## Tests previos a build

Comandos:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src tests tools launch.py
```

Resultados finales:

- pytest: `69 passed in 0.96s`
- compileall: código de salida `0`

La suite se ejecutó con acceso normal al directorio temporal del usuario y a
HKCU porque incluye una prueba real, aislada y reversible de autostart.

## Build limpia

Antes de compilar se eliminaron exclusivamente `build/`, `dist/` e
`installer/output/` de la copia FINAL.

```powershell
.\build.ps1
.\build-installer.ps1
```

Resultados:

- PyInstaller produjo una aplicación GUI `console=False` en formato ONEDIR.
- No se generó ONEFILE.
- El icono propio y la metadata PE quedaron incorporados.
- Inno Setup produjo `CodexUsageMonitor-Setup-v1.0.0.exe`.
- El instalador es por usuario, `PrivilegesRequired=lowest`, y utiliza
  `%LOCALAPPDATA%\Programs\Codex Usage Monitor`.
- Se conservaron acceso de Inicio, escritorio opcional, ejecución final,
  Restart Manager, upgrade y desinstalador.

## Seguridad

Se revisaron subprocess, quoting, rutas, HKCU, temporales, settings, IPC,
PyInstaller, carga de DLL, working directory, app-server por stdin/stdout y
tratamiento de datos no confiables.

- No existe `shell=True`.
- Codex se inicia con una lista de argumentos: ejecutable localizado,
  `app-server`, `--stdio`.
- La salida JSON se valida como objeto y el resultado se valida antes de
  convertirlo al modelo de uso.
- stderr se drena sin registrar su contenido ni rutas locales.
- Settings valida tipos/campos y escribe de forma atómica mediante un temporal
  creado en el mismo directorio.
- El autostart usa únicamente HKCU y quoting de Windows; no usa administrador
  ni Task Scheduler.
- La instancia única usa IPC local de Qt y sólo acepta la orden fija de
  restaurar/mostrar la ventana.
- No hay carga dinámica personalizada de DLL ni dependencia del CWD.
- El smoke test arrancó el ejecutable instalado con CWD fuera del workspace.

No apareció una vulnerabilidad o bug importante que exigiera alterar la
arquitectura.

## Privacidad y rate limits

- Cero telemetría, analytics, trackers o peticiones HTTP propias.
- Se utiliza el `codex app-server` local existente.
- No se lee ni empaqueta `auth.json`.
- No se guardan ni empaquetan `accountId`, tokens, cookies o credenciales.
- No se escriben logs persistentes con datos sensibles.
- La operación ejecutable de lectura es `account/rateLimits/read`.
- Se escucha `account/rateLimits/updated` para reconciliar snapshots.
- Hay cero llamadas ejecutables a
  `account/rateLimitResetCredit/consume`.
- Los reset credits se muestran exclusivamente como información y no se
  consumió ninguno durante las pruebas.

## Smoke test instalado

La instalación final se ejecutó realmente y validó:

- arranque y lectura real de rate limits;
- ventanas de 5 horas y 7 días, countdown, disponibilidad y `Reset ×N`;
- TOPMOST ON/OFF desde control y menú;
- modos compacto/completo;
- movimiento, anclaje y persistencia tras reinicio;
- bandeja, X → ocultar y restauración mediante segunda invocación;
- instancia única;
- autostart apuntando al EXE instalado, sin Python ni `_MEIPASS`;
- ejecución fuera del workspace y cierre limpio.

## Upgrade RC1 → FINAL

Prueba real completada:

1. Instalación de `1.0.0-rc1`.
2. Upgrade mediante el Setup final.
3. Una sola entrada de Aplicaciones instaladas.
4. Misma ruta y mismo AppId.
5. `DisplayVersion` final `1.0.0`.
6. Settings, autostart y preferencias conservados.
7. El EXE instalado coincidió byte a byte con el EXE de `dist`.

## Desinstalación

La desinstalación real confirmó:

- aplicación y runtime eliminados;
- accesos de Inicio y escritorio eliminados;
- entrada de Aplicaciones instaladas eliminada;
- autostart eliminado al apuntar a esa instalación;
- settings conservados;
- configuración y estado previos a la prueba restaurados al terminar.

## Auditoría de dist, instalación y ZIP

`dist` contiene 167 archivos y 116,627,735 bytes. La instalación contiene 169
archivos y 121,398,315 bytes, incluyendo el desinstalador.

En ambos casos la auditoría dio cero hallazgos para fuentes, tests, `.venv`,
`__pycache__`, caches, logs, temporales, `auth.json`, `accountId`, credenciales,
settings personales, rutas personales y `codex.exe`.

El ZIP contiene una sola carpeta superior, `CodexUsageMonitor`, con 167
archivos: `CodexUsageMonitor.exe` y su directorio `_internal`. Tamaño total sin
comprimir: 116,627,735 bytes. No incluye fuentes, tests ni `build`.

## Artefactos y hashes SHA-256

| Artefacto | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/CodexUsageMonitor/CodexUsageMonitor.exe` | 2,404,861 | `12988ECE7798F0FEF725446A3FF643A80DBFD77756085661AACE9F76D27206A7` |
| `installer/output/CodexUsageMonitor-Setup-v1.0.0.exe` | 33,488,205 | `2173023BC2B949A54222DE982094AFB67B8A4289BDBB2F60DF54986D0B3199AD` |
| `CodexUsageMonitor-Portable-v1.0.0.zip` | 46,305,259 | `18C1C0A868B0D2A3C8411BC8CDFE56321E85227E570246FA839C2D3E993B1822` |

## Configuración y licencia

- Settings: `%LOCALAPPDATA%\Codex Usage Monitor\settings.json`
- Migración: `%USERPROFILE%\.codex-usage-monitor-qt-v062.json`
- El archivo histórico no se elimina automáticamente.
- Autostart: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- LICENSE: MIT, `Copyright (c) 2026 MenghesTech`

## Limitaciones conocidas

- Windows 10/11 de 64 bits.
- Se necesita una instalación compatible de Codex para obtener uso real.
- Los binarios no están firmados digitalmente y pueden activar SmartScreen.

Codex Usage Monitor is an unofficial community project and is not affiliated
with or endorsed by OpenAI.
