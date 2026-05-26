# Arquitetura do MCVS

## Fluxo de dados

```
+-------------+      +-----------------+      +------------------+
|  Webcam     | ---> |  capture.py     | ---> |  Frame BGR + ts  |
+-------------+      +-----------------+      +------------------+
                                                       |
                          +----------------------------+
                          |                            |
                          v                            v
              +---------------------+      +----------------------+
              |  face_metrics.py    |      |  body_metrics.py     |
              |  (FaceLandmarker)   |      |  (PoseLandmarker)    |
              |  EAR, MAR, head pose|      |  tilt, FHR, vis      |
              +---------------------+      +----------------------+
                          |                            |
                          +-----------+    +-----------+
                                      |    |
                                      v    v
                          +----------------------------+
                          |  presence.py + stats.py    |
                          |  smoothing, blink, ausencia|
                          +----------------------------+
                                      |
                                      v
                          +----------------------------+
                          |  alert_engine.py           |
                          |  regras VIG-1/2/3          |
                          |  histerese + cooldown      |
                          +----------------------------+
                                      |
                          +-----------+-------------+
                          |                         |
                          v                         v
              +---------------------+   +-----------------------+
              |  event_logger.py    |   |  overlay.py           |
              |  SQLite por sessao  |   |  HUD na janela cv2    |
              +---------------------+   +-----------------------+
                                                    |
                                                    v
                                       +-----------------------+
                                       |  cv2.imshow (janela)  |
                                       |  + VideoWriter opt    |
                                       +-----------------------+
```

A cada frame, o `main.py` orquestra:

1. `capture.read()` devolve um `Frame` com imagem BGR, timestamp e índice.
2. `face_extractor.process(frame.image)` roda inferência de Face Landmarker e devolve `FaceMetrics` com EAR/MAR/yaw/pitch/roll e landmarks de desenho.
3. `body_extractor.process(frame.image)` roda inferência de Pose Landmarker e devolve `BodyMetrics` com tilt, forward head ratio e score de visibilidade por landmark.
4. `presence_tracker.update(ts, face.detected)` atualiza estado de presença/ausência.
5. `MovingMedian` suaviza EAR, MAR, yaw e pitch (janela 5 frames).
6. `BlinkCounter.update(ts, ear)` registra piscadas e expõe taxa por minuto.
7. `alert_engine.evaluate(...)` aplica as regras de VIG-1/2/3 e emite eventos novos (já filtrados por histerese e cooldown).
8. Cada evento é persistido em `event_logger.log_event(...)` no SQLite da sessão.
9. `render_hud(image, payload)` desenha overlays e painéis na imagem.
10. `cv2.imshow(...)` exibe e (se `--record` ativo) `VideoWriter.write(rendered)` grava.

## Módulos em detalhe

### capture.py
Wrapper de `cv2.VideoCapture` com fallback em ordem MSMF → DSHOW → ANY e iteração nos índices 0, 1, 2. Aplica `cv2.flip(image, 1)` para espelhar (operador vê a si mesmo na orientação correta). Devolve frame nulo se a webcam não responder, sem propagar exceção.

### face_metrics.py
Inicialização lazy do `FaceLandmarker` da API `mediapipe.tasks.python.vision`. Modelo `face_landmarker.task` baixado por `model_loader.py` em primeira execução. Cada frame é convertido para RGB, embrulhado em `mp.Image` e processado em modo VIDEO (com timestamp_ms monotonicamente crescente).

EAR usa os índices canônicos de Face Mesh: (33, 160, 158, 133, 153, 144) para olho esquerdo e (362, 385, 387, 263, 373, 380) para olho direito. MAR usa 10 landmarks ao redor da boca, computando 3 distâncias verticais médias normalizadas pela horizontal.

Head pose usa `cv2.solvePnP` com 6 landmarks faciais (nariz, queixo, cantos externos dos olhos, cantos da boca) contra um modelo 3D padrão de cabeça. Os ângulos saem em uma faixa de ±180°. Aplicamos `_wrap_around_zero` para mapear para ±90°, evitando wraparound de ~180° quando a face está orientada para frente.

### body_metrics.py
Estrutura espelha `face_metrics.py`. Inicializa `PoseLandmarker` com `min_pose_detection_confidence=0.6`. Cada landmark do MediaPipe Pose carrega um campo `visibility` que reflete o quanto o modelo tem confiança naquele ponto específico.

Computamos `shoulders_reliable` e `ears_reliable` exigindo visibilidade ≥ 0.65 em todos os pontos relevantes. Quando a confiança é baixa, devolvemos `detected=False`, e o HUD pula o desenho desses landmarks em vez de mostrar linhas em posições erradas.

`shoulder_tilt` usa `atan2(dy, abs(dx))` para ficar imune à inversão de left/right (MediaPipe Pose nomeia ombros pela perspectiva da pessoa, não da câmera, e o flip aplicado em `capture.py` mais o mirror do operador podem inverter sinal de dx).

### presence.py
`PresenceTracker` mantém `_last_seen` e `_absence_start`. Quando uma sequência de frames sem face cruza o threshold de 3s emite `absence_short`; cruzando 10s, `absence_long`.

### stats.py
- `MovingMedian` / `MovingMean`: filtros de janela fixa via `collections.deque`
- `BlinkCounter`: detecta blink quando EAR fica abaixo do threshold por ≥ 2 frames e depois volta a subir. Mantém janela móvel de 60s e expõe taxa por minuto.
- `FpsCounter`: estima FPS a partir dos últimos 30 timestamps
- `RecentExtreme`: rastreia min/max de uma métrica nos últimos N segundos. Usado pelo HUD de debug para mostrar EAR_min e MAR_max recentes (operador vê se gestos rápidos estão sendo capturados antes do filtro de duração).

### alert_engine.py
Cada categoria de evento tem um `_Sustain` próprio, com:
- `started_at`: timestamp em que a condição começou a ser verdadeira
- `fired`: se o evento já foi emitido nesta sustentação
- `cooldown_until`: timestamp até o qual essa categoria fica silenciada após emitir

O método `_maybe_emit` aplica a lógica de:
1. condição falsa → aguardar reset (com tolerância de cooldown se já fired)
2. condição verdadeira pela primeira vez → grava `started_at`
3. condição verdadeira sustentada → se `elapsed >= duration_required` e `not fired`, emite

Histerese vem do par `fired` + `cooldown_until`: o mesmo evento não pode disparar duas vezes em janela curta. Cooldown default 6s, configurável em `HysteresisConfig.cooldown_seconds`.

A severidade atual exibida no HUD vem de `_derive_current_severity`, que escolhe o pior estado ativo no momento (não soma históricos, reflete realtime).

### event_logger.py
Cria um banco SQLite por sessão, com schema duas tabelas:
- `events`: cada disparo da engine
- `session`: metadados (start_time, end_time, operator_id, total_frames, total_events)

Encoding ISO 8601 UTC em timestamps. `events.notes` carrega o valor da métrica formatado para inspeção rápida via sqlite3 CLI.

### overlay.py
Desenho composto:
- `_frame_corners`: 4 cantos em L coloridos pela severidade, dão look de visor
- `draw_face_dots`: contornos finos dos olhos e da boca + 17 pontos chave da face
- `draw_body_dots`: dois círculos nos ombros quando `shoulders_reliable`
- `_status_panel`, `_session_panel`, `_counters_panel`, `_presence_pill`: painéis fixos com `_panel` (retângulo semi-transparente com borda)
- `_debug_panel`: opcional, ligado com tecla `d`. Mostra EAR, EARmin 5s, MAR, MARmax 5s, yaw, pitch, blink/min, tilt, body visibility

### model_loader.py
Faz download lazy de `face_landmarker.task` e `pose_landmarker_lite.task` para `data/models/`. Usa atomic write (arquivo `.part` renomeado no final) para evitar arquivo corrompido se interrompido.

## Decisões de projeto

**Por que Mediapipe Tasks e não Solutions:** a partir da versão 0.10.30, o pacote `mediapipe.solutions` foi removido das builds para Python 3.13 no Windows. A API `mediapipe.tasks.python.vision` é o caminho suportado e tem inferência equivalente.

**Por que histerese:** sem cooldown, um operador piscando duas vezes ou inclinando momentaneamente a cabeça gera dezenas de eventos idênticos no log, sujando a análise pós-sessão. Histerese garante que cada estado sustentado vira no máximo um evento por janela de cooldown.

**Por que CPU-only:** ambiente acadêmico, hardware comum dos integrantes. MediaPipe Tasks com modelos float16 sustenta 15 a 30 FPS em Intel i5 moderno sem GPU.

**Por que filtro de mediana antes da engine:** EAR e MAR oscilam por ruído de detecção (especialmente em webcams com compressão agressiva). Mediana de 5 frames remove spikes sem suavizar demais transições legítimas de blink.

**Por que MIN_VISIBILITY no body:** sem isso, o sistema renderiza linhas de ombro em posições erradas quando o operador está sentado com torso parcialmente cortado pelo enquadramento, ou em iluminação ruim. Visibility ≥ 0.65 é um threshold conservador que cobre os casos de baixa qualidade sem ser restritivo demais.
