from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.event_logger import load_events


SEVERITY_ORDER = ["VIG-3", "VIG-2", "VIG-1"]
SEVERITY_COLOR = {
    "VIG-1": "#d83434",
    "VIG-2": "#e6b517",
    "VIG-3": "#3a8bd1",
}
SEVERITY_Y = {"VIG-3": 1, "VIG-2": 2, "VIG-1": 3}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay e analise de sessao MCVS")
    parser.add_argument("db", type=Path, help="caminho do SQLite gerado por main.py")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="caminho de saida do PNG da timeline",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="nao abrir janela do matplotlib. apenas salvar PNG se --output for dado",
    )
    return parser.parse_args()


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_timeline(events: List[dict], session: Dict, output: Path | None, show: bool) -> None:
    if not events:
        print("sessao sem eventos registrados")
        return

    times = [_parse_ts(e["timestamp"]) for e in events]
    severities = [e["severity"] for e in events]
    ys = [SEVERITY_Y.get(s, 0) for s in severities]
    colors = [SEVERITY_COLOR.get(s, "#888888") for s in severities]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.scatter(times, ys, c=colors, s=80, edgecolors="black", linewidths=0.6, zorder=3)

    for t, y, evt in zip(times, ys, events):
        ax.annotate(
            evt["event_type"],
            (t, y),
            textcoords="offset points",
            xytext=(0, 8),
            fontsize=7,
            ha="center",
            color="#444444",
        )

    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(["VIG-3", "VIG-2", "VIG-1"])
    ax.set_ylim(0.4, 3.6)
    ax.set_xlabel("tempo UTC")
    ax.set_title("MCVS timeline de eventos por severidade")
    ax.grid(True, alpha=0.25, zorder=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()

    if session:
        start = session.get("start_time", "")
        end = session.get("end_time", "")
        operator = session.get("operator_id", "")
        fig.suptitle(
            f"operador {operator}  inicio {start}  fim {end}",
            fontsize=9,
            y=0.99,
        )

    fig.tight_layout()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=130)
        print(f"timeline salva em {output}")
    if show:
        plt.show()
    plt.close(fig)


def summarize(events: List[dict], session: Dict) -> None:
    counts = Counter(e["severity"] for e in events)
    by_type: Dict[str, int] = Counter(e["event_type"] for e in events)
    durations: Dict[str, float] = defaultdict(float)
    for e in events:
        if e.get("duration_seconds"):
            durations[e["event_type"]] += float(e["duration_seconds"])

    print("=" * 60)
    print("RESUMO DA SESSAO")
    print("=" * 60)
    if session:
        print(f"operador        : {session.get('operator_id', '')}")
        print(f"inicio          : {session.get('start_time', '')}")
        print(f"fim             : {session.get('end_time', '')}")
        print(f"frames totais   : {session.get('total_frames', 0)}")
        print(f"eventos totais  : {session.get('total_events', 0)}")
    print("-" * 60)
    print("eventos por severidade")
    for sev in SEVERITY_ORDER:
        print(f"  {sev}: {counts.get(sev, 0)}")
    print("-" * 60)
    print("eventos por tipo")
    for evt_type, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
        dur = durations.get(evt_type, 0.0)
        print(f"  {evt_type:18s} count={count:3d}  duration_total={dur:6.1f}s")
    print("-" * 60)

    micros = by_type.get("microsleep", 0)
    yawns = by_type.get("yawn", 0)
    distraction = by_type.get("distraction", 0)
    absence_long = by_type.get("absence_long", 0)
    critical_total = counts.get("VIG-1", 0)

    if micros >= 2 or absence_long >= 2:
        print("recomendacao: pausa imediata. operador apresentou eventos criticos recorrentes")
    elif critical_total >= 1:
        print("recomendacao: revisar sessao com supervisor. ao menos um evento VIG-1 registrado")
    elif yawns >= 3 or distraction >= 3:
        print("recomendacao: pausa curta sugerida. sinais de fadiga ou distracao acumulados")
    else:
        print("recomendacao: operador em estado adequado para continuar sessao")
    print("=" * 60)


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        print(f"arquivo nao encontrado: {args.db}", file=sys.stderr)
        return 1

    events, session = load_events(args.db)
    summarize(events, session)
    build_timeline(events, session, args.output, show=not args.no_show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
