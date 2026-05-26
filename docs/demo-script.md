# Roteiro do vídeo de demonstração

Alvo: 4 a 5 minutos. Gravar com OBS Studio capturando a janela do programa, voz over opcional.

## Setup antes de gravar

- Posto físico com webcam funcional. Se a webcam disponível tem qualidade baixa (artefatos de cor, banding), considerar uma das alternativas:
  - Webcam externa USB 720p ou superior emprestada para a gravação
  - App de webcam virtual usando câmera de celular (Iriun Webcam, DroidCam)
  - Outro integrante do grupo grava no notebook com webcam melhor
- Iluminação frontal estável. Janela ou luminária na frente do operador, não atrás.
- Fundo neutro, sem outras pessoas circulando.
- Plano cheio até o tórax do operador (ombros visíveis, espaço acima da cabeça).
- Áudio: microfone do notebook serve. Se gravar voz over depois em vez de live, melhor qualidade.
- Antes de gravar: rodar `python scripts/calibrate_thresholds.py --duration 30` com o operador que vai aparecer no vídeo. Garante que os thresholds estão ajustados.

## Roteiro por cena

| Cena | Duração | Conteúdo |
|---|---|---|
| 1. Abertura | 0:00 a 0:20 | Slide ou cartela inicial com título "OrbittAPI Mission Control Vigilance System", subtítulo "Global Solution 2026.1 - Physical Computing IoT/IoB", logo do grupo, nomes dos integrantes. |
| 2. Contexto | 0:20 a 0:50 | Voz over: "A OrbittAPI entrega dados satelitais que sustentam decisões agroambientais com cascata real no campo. Quem opera essa plataforma precisa de vigilância sustentada. O Mission Control Vigilance System monitora o estado do operador em tempo real usando uma webcam comum como sensor IoB." Mostrar um screenshot da OrbittAPI ou imagem genérica de sala de controle. |
| 3. Arquitetura | 0:50 a 1:20 | Mostrar o diagrama de fluxo (presente em docs/arquitetura.md). Voz over: "A webcam alimenta dois detectores em paralelo: Face Landmarker e Pose Landmarker. As métricas vão para uma engine de regras com histerese que classifica o estado em três níveis de severidade. Eventos são persistidos em SQLite e o HUD é renderizado em tempo real." |
| 4. Demo estado OK | 1:20 a 1:50 | Operador na webcam, postura ereta, olhando para a câmera. HUD mostra STATUS OK em verde, todas as métricas dentro do normal, V1/V2/V3 zerados. Apertar `d` para mostrar o painel de debug e comentar os números: EAR 0.30, MAR 0.18, blink/min entre 12 e 20, body vis ~0.95. |
| 5. Demo bocejo (VIG-2) | 1:50 a 2:20 | Operador abre a boca em bocejo grande e sustenta por 4 segundos. MAR sobe acima de 0.60. STATUS muda para ATENCAO em amarelo. Contador V2 incrementa de 0 para 1. Pode comentar: "MAR cruzou o threshold de bocejo, sistema marcou evento VIG-2." |
| 6. Demo distração (VIG-2) | 2:20 a 2:50 | Operador vira a cabeça lateralmente por 5 segundos. yaw passa de 30°. STATUS amarelo, V2 incrementa para 2. Comentário: "Yaw acima de 30 graus por mais de 5 segundos disparou o evento de distração." |
| 7. Demo microsono (VIG-1) | 2:50 a 3:30 | Operador fecha os olhos firmemente e mantém por 2 segundos. EAR cai abaixo de 0.15. STATUS muda para CRITICO em vermelho. V1 incrementa para 1. Cantos do frame ficam vermelhos também. Comentário: "Esse é o evento mais crítico. O sistema detectou microsono e emitiu alerta VIG-1." |
| 8. Demo ausência (VIG-1) | 3:30 a 4:00 | Operador sai do enquadramento por 11 segundos. HUD muda para AUSENTE em vermelho, contador de absence em segundos sobe. Após 10s, evento VIG-1 absence_long é registrado. Comentário: "Quando o rosto sai do quadro por mais de 10 segundos, o sistema marca ausência longa como crítico." |
| 9. Replay e análise | 4:00 a 4:40 | Encerrar a sessão com `q`. Rodar `python scripts/replay_log.py data/logs/session_xxx.db --output outputs/timeline.png`. Mostrar o terminal com o resumo (contagem por severidade, recomendação textual). Abrir o PNG da timeline e comentar: "Cada evento da sessão aparece na linha do tempo, colorido por severidade." |
| 10. Fechamento | 4:40 a 5:00 | Cartela final: "OrbittAPI MCVS - parte da Global Solution 2026.1. Frente IoT/IoB integrada com backend SOA, mobile, cybersecurity e IA/ML do mesmo grupo. Repositório público no GitHub." Lista os integrantes e seus RMs. |

## Sugestão de gravação

1. **Modo voz over.** Grava as cenas de webcam primeiro sem narrar, depois narra em cima. Reduz pressão durante a captura e a voz fica mais limpa.
2. **OBS scenes:**
   - Scene 1: janela do programa em fullscreen
   - Scene 2: terminal do PowerShell para mostrar o `replay_log.py`
   - Scene 3: visualizador de imagem para mostrar a timeline PNG
3. **Bitrate:** 5000 kbps a 1080p, 30 FPS. Arquivo final ~150MB em 5 minutos.
4. **Codec:** H.264. MP4. Compatível com YouTube.

## Onde publicar

- YouTube unlisted ou público (preferido)
- Link colocado no README.md, na seção "Vídeo demonstrativo"
- Backup: GitHub Releases (anexo no release v1.0.0 do repo)

## Checklist pré-gravação

- [ ] `python scripts/calibrate_thresholds.py` rodado com o operador da gravação
- [ ] Iluminação frontal estável
- [ ] Webcam testada (rodar `python main.py` 1 minuto antes e ver se chega a 15+ FPS)
- [ ] Outro app não está segurando a webcam (Teams, Zoom, OBS scene com webcam dupla, navegador)
- [ ] Ambiente sem distrações (notificações desligadas)
- [ ] Roteiro mental dos 5 cenários: OK, bocejo, distração, microsono, ausência
- [ ] Plano B para webcam ruim definido antes de começar
