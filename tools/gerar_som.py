"""Gera o som do aviso das rotinas: hub/web/static/aviso.wav.

Um "plim-plim-plom" curto e suave, de três notas, como o aviso de um aeroporto. Feito só com a
biblioteca padrão (wave e math), sem baixar nada. O arquivo gerado vai junto no projeto; só
rode de novo se quiser mudar o som:

    .venv\\Scripts\\python -m tools.gerar_som
"""

import io
import math
import struct
import wave
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "hub" / "web" / "static" / "aviso.wav"
RATE = 16000  # 16 kHz em mono basta para um sino e deixa o arquivo pequeno (~60 KB)
NOTES = ((0.00, 784.0), (0.30, 659.3), (0.60, 523.3))  # sol, mi e dó: (quando começa em segundos, frequência)
PARTIALS = ((1.0, 1.0), (2.0, 0.28), (3.0, 0.08), (4.2, 0.04))  # harmônicos de sino: (múltiplo, volume)
DECAY = 0.42  # segundos para cada nota cair a ~37%
LENGTH = 2.0  # segundos
VOLUME = 0.55  # pico, de 0 a 1: alto o bastante para a sala, sem estourar


def samples() -> list[float]:
    total = int(RATE * LENGTH)
    out = [0.0] * total
    for start, freq in NOTES:
        first = int(start * RATE)
        for i in range(total - first):
            t = i / RATE
            attack = min(1.0, t / 0.006)  # 6 ms de entrada: sem estalo no começo
            envelope = attack * math.exp(-t / DECAY)
            out[first + i] += envelope * sum(v * math.sin(2 * math.pi * freq * m * t) for m, v in PARTIALS)
    fade = int(0.15 * RATE)  # termina em silêncio, sem corte seco
    for i in range(fade):
        out[total - fade + i] *= 1 - i / fade
    peak = max(abs(x) for x in out)
    return [x / peak * VOLUME for x in out]


def build() -> bytes:
    """O conteúdo do .wav (sempre o mesmo: nada aleatório)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", round(x * 32767)) for x in samples()))
    return buffer.getvalue()


if __name__ == "__main__":
    TARGET.write_bytes(build())
    print(f"{TARGET} ({TARGET.stat().st_size // 1024} KB)")
