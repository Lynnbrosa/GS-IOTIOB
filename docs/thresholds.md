# Thresholds e como ajustar

Todos os thresholds default vivem em `src/config.py` nas dataclasses `FaceThresholds`, `BodyThresholds`, `PresenceThresholds` e `HysteresisConfig`. O `scripts/calibrate_thresholds.py` produz um JSON em `data/calibration.json` que sobrescreve os defaults na próxima execução.

## Face (FaceThresholds)

| Campo | Default | Significado | Quando ajustar |
|---|---|---|---|
| `ear_microsleep` | 0.15 | EAR abaixo disto conta como olho fechado | Subir para 0.18 se o operador tem olhos amendoados (baseline já é baixo). Descer para 0.12 se EAR baseline é > 0.35. |
| `ear_microsleep_duration_s` | 1.5 | Quanto tempo o EAR precisa ficar abaixo do threshold para disparar VIG-1 | Subir para 2.0 se houver muitos falsos positivos em piscadas longas. Não descer abaixo de 1.0 (corta blinks normais). |
| `ear_blink_threshold` | 0.21 | EAR abaixo disto conta uma piscada | Geralmente 70% do EAR baseline. Ajuste por calibração. |
| `ear_blink_min_frames` | 2 | Mínimo de frames consecutivos abaixo do blink threshold para contar piscada | Aumentar para 3 se webcam é instável e gera flicker. |
| `mar_yawn` | 0.60 | MAR acima disto conta como boca aberta sustentada | Descer para 0.50 se o operador tem boca pequena (MAR raramente passa de 0.55). |
| `mar_yawn_duration_s` | 4.0 | Quanto tempo o MAR precisa ficar acima do threshold para disparar bocejo | Descer para 3.0 em ambiente que tolera falsos positivos. Subir para 5.0 se quiser só bocejos longos confirmados. |
| `yaw_distraction_deg` | 30.0 | Ângulo horizontal absoluto acima do qual conta como distração | Subir se a câmera está mal posicionada e o operador olha ligeiramente fora do centro só por estar olhando o monitor. |
| `pitch_distraction_deg` | 30.0 | Ângulo vertical absoluto acima do qual conta como distração | Subir se o operador trabalha com tela baixa ou notas físicas. |
| `distraction_duration_s` | 5.0 | Quanto tempo o yaw ou pitch precisa ficar acima do threshold | Tolerância para o operador olhar rápido um alerta lateral. |
| `blink_rate_min` | 8.0 | Piscadas por minuto abaixo disto é anomalia | Foco intenso reduz blink rate. Descer para 6 se for tarefa de leitura concentrada. |
| `blink_rate_max` | 25.0 | Piscadas por minuto acima disto é anomalia | Fadiga ou olhos secos elevam blink rate. Subir para 30 se o ambiente é seco demais. |
| `blink_anomaly_window_s` | 120.0 | Janela em que a anomalia de blink rate precisa se sustentar | Duração curta gera ruído. Duração longa atrasa detecção. 2 min é um meio termo. |

## Body (BodyThresholds)

| Campo | Default | Significado | Quando ajustar |
|---|---|---|---|
| `shoulder_tilt_deg` | 8.0 | Inclinação absoluta dos ombros acima da qual conta como má postura | Subir para 12° se o operador trabalha de lado em mesa em L. |
| `forward_head_ratio` | 0.25 | Distância horizontal orelha-ombro normalizada pela largura dos ombros | Descer para 0.20 se o objetivo é ergonomia estrita. |
| `posture_duration_s` | 10.0 | Tempo de má postura sustentada para disparar VIG-3 | Subir para 15s para tolerar movimentos curtos. |

## Presence (PresenceThresholds)

| Campo | Default | Significado | Quando ajustar |
|---|---|---|---|
| `short_absence_min_s` | 3.0 | Sem rosto por mais que isso conta como ausência curta (VIG-3) | Descer para 2s em ambientes com alta criticidade. |
| `long_absence_min_s` | 10.0 | Sem rosto por mais que isso conta como ausência longa (VIG-1) | Subir para 15s se o operador frequentemente vira para consultar material físico. |

## Hysteresis (HysteresisConfig)

| Campo | Default | Significado | Quando ajustar |
|---|---|---|---|
| `cooldown_seconds` | 6.0 | Tempo de silêncio por categoria após disparo | Subir para 10s se o log estiver cheio de eventos repetidos. Descer para 3s se quiser captura mais granular. |
| `smoothing_window` | 5 | Tamanho do filtro de mediana móvel para EAR/MAR/yaw/pitch | Aumentar para 7 em webcam ruidosa. Reduzir para 3 se quiser resposta mais rápida (em troca de mais falsos positivos por flicker). |

## Calibração automática

```bash
python scripts/calibrate_thresholds.py --duration 30
```

O script faz:

1. Pede para o operador olhar para a câmera com expressão neutra por 30 segundos
2. Coleta EAR, MAR, yaw e pitch a cada frame
3. Computa baselines via mediana das amostras
4. Deriva thresholds:
   - `ear_microsleep = max(0.10, ear_baseline * 0.55)`
   - `ear_blink_threshold = max(0.16, ear_baseline * 0.72)`
   - `mar_yawn = max(0.40, mar_baseline + 0.30)`
   - `yaw_distraction_deg = max(15.0, |yaw_baseline| + 25.0)`
   - `pitch_distraction_deg = max(15.0, |pitch_baseline| + 25.0)`
5. Salva em `data/calibration.json` (gitignored, único por máquina/operador)

## Exemplo de calibration.json

```json
{
  "operator_id": "operator_01",
  "face": {
    "ear_microsleep": 0.14,
    "ear_blink_threshold": 0.20,
    "mar_yawn": 0.55,
    "yaw_distraction_deg": 28.0,
    "pitch_distraction_deg": 22.0
  },
  "body": {},
  "presence": {},
  "hysteresis": {}
}
```

Campos ausentes herdam os defaults. Você pode editar `calibration.json` à mão para sobrescrever só o que precisar mudar (não precisa rodar o calibrate todo de novo).
