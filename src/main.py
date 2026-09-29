import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from .widget import Monitor
from .app_paths import resource_path

SERVER_NAME = "CodexUsageMonitor-OpenAI-unofficial-v090"

def notify_existing():
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(350):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(200)
        sock.disconnectFromServer()
        return True
    return False

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Codex Usage Monitor")
    app.setApplicationDisplayName("Codex Usage Monitor")
    app.setApplicationVersion("1.0.0")
    icon = resource_path("assets", "CodexUsageMonitor.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    app.setQuitOnLastWindowClosed(False)

    if notify_existing():
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        if notify_existing():
            return 0
        raise RuntimeError("No se pudo crear la instancia única de Codex Usage Monitor.")

    w = Monitor()

    def incoming():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            if conn:
                conn.waitForReadyRead(100)
                w.show()
                w.raise_()
                w.activateWindow()
                conn.disconnectFromServer()

    server.newConnection.connect(incoming)
    app._monitor = w
    app._single_instance_server = server
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
