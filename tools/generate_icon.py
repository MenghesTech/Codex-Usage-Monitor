from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen


def main() -> int:
    QGuiApplication.instance() or QGuiApplication([])
    root = Path(__file__).resolve().parent.parent
    output = root / "assets" / "CodexUsageMonitor.ico"
    output.parent.mkdir(parents=True, exist_ok=True)

    size = 256
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#45e66a"))
    painter.drawEllipse(12, 12, 232, 232)
    painter.setPen(QPen(QColor("#0a121d"), 28))
    font = QFont("Segoe UI", 124)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignCenter, "C")
    painter.end()

    if not image.save(str(output), "ICO"):
        raise RuntimeError("Qt no pudo generar el icono ICO")
    print(output.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
