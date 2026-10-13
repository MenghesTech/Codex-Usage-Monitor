# Codex Usage Monitor

> **Codex Usage Monitor is an unofficial community project and is not
> affiliated with or endorsed by OpenAI.**

Codex Usage Monitor es un widget local para Windows que muestra el porcentaje
usado de Codex en las ventanas de 5 horas y 7 días. Se comunica en modo lectura
con el `codex app-server` que ya exista en el equipo.

![Widget completo](docs/screenshots/widget-full.png)

## Características

- Ventanas de uso de 5 horas (`primary`) y 7 días (`secondary`).
- `usedPercent` representa porcentaje **usado**, no restante.
- Cuenta atrás calculada a partir del `resetsAt` del último snapshot completo.
- Estado de disponibilidad basado en `ordinaryUsageAllowed`.
- Reset credits mostrados únicamente como información; nunca se consumen.
- Modos completo y compacto.
- Opción `Siempre visible` (TOPMOST).
- Bandeja del sistema, anclaje a pantalla e instancia única.
- Alertas locales configurables con hasta tres porcentajes del 1 al 100 por
  ventana. Comienzan desactivadas.
- Inicio opcional con Windows mediante HKCU, sin privilegios de administrador.
- Detección periódica de Codex: el monitor puede recuperarse si Codex se
  instala mientras permanece abierto.

Si no existe un `codex.exe` compatible, la aplicación sigue funcionando y
muestra `Codex no encontrado`. Si el ejecutable existe pero su app-server
falla, muestra `Error de Codex`.

## Requisitos

- Windows 10 u 11 de 64 bits.
- Una instalación compatible de Codex CLI o de la extensión oficial de Codex
  para VS Code, necesaria para obtener los límites reales.

El instalador incluye el runtime necesario: no requiere Python, workspace ni
entorno virtual en el equipo de destino. No incluye ni instala `codex.exe`.

## Instalación

Descarga el instalador desde
[GitHub Releases](https://github.com/MenghesTech/Codex-Usage-Monitor/releases)
cuando la release esté publicada y ejecuta
`CodexUsageMonitor-Setup-v1.0.0.exe`. La instalación es por usuario, sin UAC,
en `%LOCALAPPDATA%\Programs\Codex Usage Monitor`. Crea un acceso en Inicio y
permite añadir un acceso directo de escritorio.

La aplicación no está firmada digitalmente. SmartScreen o el antivirus pueden
mostrar una advertencia para un ejecutable sin firma.

## Configuración y autostart

Las preferencias se guardan en:

```text
%LOCALAPPDATA%\Codex Usage Monitor\settings.json
```

Se conservan posición, anclaje, modo compacto, TOPMOST y alertas. Si la ruta nueva aún
no existe, se migran los campos conocidos desde
`%USERPROFILE%\.codex-usage-monitor-qt-v062.json`; el archivo histórico no se
elimina automáticamente.

### Alertas de uso

Abre `Configurar alertas…` desde el menú de bandeja o el menú contextual del
widget. La ventana permite activar o desactivar todos los avisos y escribir
hasta tres porcentajes enteros del 1 al 100 para cada límite (5 horas y 7 días).
Puedes dejar campos vacíos para tener menos avisos. No se admiten porcentajes
repetidos dentro de una ventana; al guardar, se ordenan automáticamente.
Desactivar las alertas conserva los porcentajes para una activación posterior.
Las instalaciones nuevas comienzan con las alertas desactivadas y los campos
vacíos. Las preferencias existentes con umbrales fijos 80 %, 90 % y 95 % se
migran a los campos correspondientes; los umbrales previamente activados y el
estado de deduplicación del ciclo se conservan.

El aviso se envía al cruzar un umbral desde una lectura inferior. Si activas
una alerta con el uso ya por encima, no aparece un aviso retroactivo. Los
umbrales cruzados en una misma lectura se agrupan en una notificación. El
estado de avisos emitidos se conserva en `settings.json` para evitar repeticiones
al reiniciar la aplicación durante el mismo ciclo. Un nuevo ciclo de reset
permite nuevos avisos. Las lecturas incompletas no generan alertas; el
comportamiento visual de la notificación depende de la configuración de Windows.

Para distinguir un reset real de una corrección de `resetsAt`, el monitor exige
que el deadline avance al menos la mitad de la duración de la ventana y que el
consumo disminuya. Si el servicio no ofrece esas señales, no puede identificarse
el ciclo con certeza y el monitor conserva la deduplicación del ciclo anterior.

Los avisos pendientes se guardan antes de enviarse a la bandeja. Un fallo
temporal de escritura o de `showMessage()` se reintenta con las siguientes
lecturas; desactivar un umbral cancela sus avisos pendientes. `showMessage()`
solo confirma que Qt aceptó la llamada, no que Windows mostrase el aviso. Si
la aplicación se cierra mientras el disco sigue inaccesible, un aviso aún no
guardado puede perderse. Si se cierra después de enviarlo pero antes de guardar
su confirmación, puede repetirse al reiniciar. Por ello no se garantiza una
entrega exactamente una vez.

Para comprobar visualmente las notificaciones de Windows sin consultar Codex ni
modificar tus ajustes reales, ejecuta desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe tests\manual_windows_notifications.py
```

El arnés usa un `settings.json` temporal y muestra su ruta. En el widget o la
bandeja, abre `Configurar alertas…`, activa las alertas, introduce `80`, `90` y
`95` para ambas ventanas y pulsa `Guardar`. En el panel de pruebas, pulsa
`79 % / 79 %` y después `96 % / 96 %`: debe aparecer un único aviso con los
seis cruces. `Repetir lectura` y `Reiniciar widget` no deben repetirlo. Usa
`Nuevo ciclo: 5 % / 5 %` y vuelve a cruzar un umbral para comprobar el rearme.
Prueba también `Cancelar`, campos vacíos, porcentajes duplicados, desactivar el
control general y `Ocultar / mostrar widget`; las notificaciones deben seguir
llegando a la bandeja con el widget oculto. El arnés elimina su configuración
temporal al cerrarse. Windows puede ocultar los avisos según sus ajustes de
notificaciones.

`Abrir al iniciar Windows` utiliza exclusivamente el valor por usuario
`CodexUsageMonitor` de `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

## Privacidad

- Funciona localmente y usa el `codex app-server` local existente.
- No implementa telemetría, analytics, trackers ni peticiones HTTP propias.
- No lee ni empaqueta `auth.json`.
- No copia tokens, cookies, credenciales ni cabeceras de autorización.
- No muestra ni persiste identificadores de cuenta.
- Solicita `account/rateLimits/read` y escucha
  `account/rateLimits/updated`.
- No llama a `account/rateLimitResetCredit/consume`.

El proceso de Codex conserva la responsabilidad de su conexión y autenticación.
El monitor procesa únicamente los límites de uso devueltos por ese proceso.

## Desinstalación

Desinstala desde Configuración de Windows > Aplicaciones instaladas. Se
eliminan aplicación, runtime, accesos directos y la entrada de autostart si
apunta al EXE instalado. Los settings se conservan para evitar pérdida de
preferencias.

## Desarrollo y build

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
powershell -ExecutionPolicy Bypass -File .\build.ps1
powershell -ExecutionPolicy Bypass -File .\build-installer.ps1
```

La build es GUI (`console=False`) y ONEDIR; no se utiliza ONEFILE. La metadata
PE es `1.0.0.0` y la versión de producto es `1.0.0`.

## Licencia y marcas

Código bajo licencia [MIT](LICENSE), copyright © 2026 MenghesTech.

“OpenAI”, “ChatGPT” y “Codex” son marcas de sus respectivos titulares. El
nombre se usa de forma descriptiva para indicar compatibilidad. El icono propio
no utiliza logotipos oficiales de OpenAI o ChatGPT.
