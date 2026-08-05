

# Whiteboard Video

[English](README.en.md)

**Ingresa un tema y genera un video explicativo de infografía en pizarra blanca de 30 a 60 segundos generado por IA.**

<p align="center">
  <img src="https://raw.githubusercontent.com/zkbys/whiteboard/main/assets/demo.gif" width="720" alt="Video de demostración: Tema «Cuanto más herramientas de IA, menos eficientes son las personas comunes» (acelerado 1.25×)">
  <br>
</p>

## 🚀 Inicio rápido

**Copia el siguiente mensaje y envíalo directamente a tu asistente de programación con IA:**

```
请安装这个项目：https://github.com/zkbys/whiteboard.git

阅读 README 后运行：
python3 scripts/install.py --target codex   # Codex
python3 scripts/install.py --target claude  # Claude Code

安装完成后运行：
python3 scripts/doctor.py --json

然后帮我做一个视频，主题是「AI 工具越多，普通人反而越低效」，时长 30-60 秒。
```

El video se generará en `whiteboard-runs/<run-id>/video/preview.mp4` dentro del directorio actual.

## Instalación por línea de comandos

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard

# Codex
python3 scripts/install.py --target codex
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json

# Claude Code
python3 scripts/install.py --target claude
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json
```

Instalar en ambos destinos: `--target both`. No escribir en vista previa: `--dry-run`. Actualizar: `--upgrade`.

## Qué se obtiene con una ejecución

```text
whiteboard-runs/<run-id>/
├── script/                    # Guion de voz en off y ritmo visual
├── infographic/               # Planificación de infografía
├── images/*.model-generated.png   # Imágenes de pizarra generadas por el modelo
├── calibration/               # Calibración automática/manual de bboxes de elementos
├── board_source_for_e/        # Capa de control de animación
├── audio/                     # Voz en off, subtítulos, línea de tiempo
├── sync/                      # Informe de QA de /acciones/tomas
├── video/
│   ├── preview.mp4            # Video final
│   ├── hyperframes/           # Proyecto editable
│   └── keyframes/             # Fotogramas clave
└── integration_report.md      # Informe de aceptación
```

Una vez finalizada la renderización, puedes ejecutar el validador v1:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /absolute/path/to/whiteboard-run
```

## Requisitos del entorno

- Python 3.10+
- Node.js 20+
- `ffmpeg`, `ffprobe`
- `edge-tts`, `npx`
- `hyperframes@0.6.99`

```bash
python3 scripts/doctor.py        # Informe en texto
python3 scripts/doctor.py --json # Informe en JSON
```

Doctor verifica cuatro niveles de estado:

| Categoría | Descripción |
|------|------|
| `install` | Si el Skill en sí y sus módulos internos están completos |
| `render` | Si Python/Node/ffmpeg/edge-tts/HyperFrames están listos |
| `output` | Si el directorio de salida es escribible |
| `image` | Si el modo de imagen es `interactive` (predeterminado, sin clave) o `auto` |

## Modo de imagen

Modo predeterminado `interactive`: El asistente de IA se pausa una vez tras generar la imagen, espera a que confirmes que se ha guardado en la ruta indicada y luego reanuda automáticamente el flujo de trabajo.

Modo automático (requiere la clave API de OpenAI):

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=openai
export OPENAI_API_KEY="..."
```

Configurar solo la clave no generará cargos; debes establecer simultáneamente `WHITEBOARD_IMAGE_PROVIDER=openai`.

## Calibración automática

La Fase D (capa de control de animación) dibuja de forma predeterminada líneas rojas, recuadros y tomas usando coordenadas de plantillas. Cuando las imágenes generadas por el modelo (por ejemplo, seedance) se desvían del diseño de la plantilla, las etiquetas se desplazan. La tubería detecta automáticamente la posición real de los elementos a partir del PNG real antes de la Fase D:

```bash
python3 hand-drawn-infographic-video-board/scripts/auto_calibrate.py \
  --project-dir whiteboard-runs/<run-id> \
  --provider auto \
  --json
```

- `agent`: Usa el modelo visual de Claude (recomendado, vía `ANTHROPIC_AUTH_TOKEN`), sin necesidad de configurar por separado `OPENAI_API_KEY`. `--provider auto` intentará automáticamente el agente si no se ha configurado `OPENAI_API_KEY`.
- `vlm`: Interfaz compatible con OpenAI (requiere `OPENAI_API_KEY`).
- `ocr`: OCR local (sin costos de API): `pip install easyocr`.
- `mock`: Coordenadas de marcador de posición deterministas, para pruebas o como respaldo cuando no hay backends disponibles.

Si la detección automática no cubre todos los elementos objetivo, se generará la herramienta de calibración prellenada `calibration_tool/index.html`. Tras ajustarla manualmente, guárdala en `calibration/` y vuelve a ejecutar las fases D/E.

Salida de la calibración automática:

```text
calibration/<boardId>.element_bboxes.json
calibration/auto_calibration_report.json
```

## Limitaciones conocidas

- No busca cachés ocultos, no falsifica URL de imágenes ni usa marcadores de posición para suplir salidas del modelo
- La calibración automática admite agent, VLM y OCR local; el OCR local requiere la instalación adicional de `easyocr`/`paddleocr`

## Desarrollo

Tubería interna: Tema → Guion de voz (B) → Planificación (C) → Generación de imágenes (Creator) → Capa de control (D) → Renderizado/QA (E)

Antes de desarrollar, lee [AGENTS.md](AGENTS.md), [Estructura del proyecto](docs/PROJECT_STRUCTURE.md) y [Contrato de arquitectura](docs/ARCHITECTURE.md). Ejecuta antes de enviar los cambios:

```bash
npm run check
```

## Licencia

MIT.
