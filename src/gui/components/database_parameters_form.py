import os
from dotenv import load_dotenv
from PyQt6.QtWidgets import QWidget, QFormLayout, QLineEdit, QSpinBox
from PyQt6.QtCore import pyqtSignal, Qt

load_dotenv()

DEFAULT_PORTS = {
    "MYSQL": 3306,
    "POSTGRESQL": 5432,
}


class DatabaseParametersForm(QWidget):
    """Форма для ввода параметров БД"""

    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.user_input = QLineEdit()
        self.user_input.setText(os.getenv("MYSQL_USER", ""))

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setText(os.getenv("MYSQL_PASSWORD", ""))

        self.host_input = QLineEdit()
        self.host_input.setText(os.getenv("MYSQL_HOST", "localhost"))

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(os.getenv("MYSQL_PORT", 3306)))

        self.database_input = QLineEdit()
        self.database_input.setText(os.getenv("MYSQL_DATABASE", ""))

        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("User", self.user_input)
        layout.addRow("Password", self.password_input)
        layout.addRow("Host", self.host_input)
        layout.addRow("Port", self.port_input)
        layout.addRow("Database", self.database_input)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.setLayout(layout)

    def load_from_env(self, prefix: str):
        default_port = DEFAULT_PORTS.get(prefix, 3000)

        self.user_input.setText(os.getenv(f"{prefix}_USER", ""))
        self.password_input.setText(os.getenv(f"{prefix}_PASSWORD", ""))
        self.host_input.setText(os.getenv(f"{prefix}_HOST", "localhost"))
        self.port_input.setValue(int(os.getenv(f"{prefix}_PORT", default_port)))
        self.database_input.setText(os.getenv(f"{prefix}_DATABASE", ""))
        self.log_message.emit(
            f"Загружены параметры подключения из .env [{prefix}]", "INFO"
        )

    def get_params(self) -> dict:
        return {
            "user": self.user_input.text(),
            "password": self.password_input.text(),
            "host": self.host_input.text(),
            "port": self.port_input.value(),
            "database": self.database_input.text(),
        }

    def set_params(self, params: dict):
        self.user_input.setText(params.get("user", ""))
        self.password_input.setText(params.get("password", ""))
        self.host_input.setText(params.get("host", ""))
        self.port_input.setValue(int(params.get("port", 3306)))
        self.database_input.setText(params.get("database", ""))
