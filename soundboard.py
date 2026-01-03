import sys
import os
import pactl

session = os.environ.get("XDG_SESSION_TYPE", "").lower()

if session == "x11":
    import keyboard

import sounddevice as sd
import soundfile as sf

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout,QKeySequenceEdit,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QLabel
)
from PySide6.QtCore import QSettings, QTimer, Qt


# ---------------- AUDIO ----------------
def load_audio(path):
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


# ---------------- HOTKEY DIALOG ----------------
if session == "x11":
    class HotkeyDialog(QDialog):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Назначить хоткей")
            self.setModal(True)

            self.key = None

            layout = QVBoxLayout(self)

            hint = QLabel("Нажми комбинацию клавиш")
            hint.setAlignment(Qt.AlignCenter)
            layout.addWidget(hint)

            self.edit = QKeySequenceEdit()
            self.edit.clear()
            layout.addWidget(self.edit)

            btns = QHBoxLayout()

            apply_btn = QPushButton("Применить")
            cancel_btn = QPushButton("Отмена")

            apply_btn.clicked.connect(self.apply)
            cancel_btn.clicked.connect(self.reject)

            btns.addWidget(apply_btn)
            btns.addWidget(cancel_btn)

            layout.addLayout(btns)

        def apply(self):
            seq = self.edit.keySequence().toString()
            if seq:
                # Qt: "Shift+W" → keyboard: "shift+w"
                self.key = seq.lower().replace("+", "+")
                self.accept()

# ---------------- MAIN WINDOW ----------------
class SoundboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Soundboard Ulta Pro Max")
        self.resize(420, 520)

        self.settings = QSettings("Soundboard", "Hotkeys")
        self.sounds = {}
        self.hotkey_ids = {}

        self.init_ui()
        self.load_sounds()
        if session == "x11":
            self.register_hotkeys()

    # ---------- UI ----------

    def init_ui(self):
        central = QWidget()
        layout = QVBoxLayout()

        title = QLabel("🎵 Soundboard")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.list = QListWidget()
        layout.addWidget(self.list)

        btns = QHBoxLayout()

        add_btn = QPushButton("➕")
        del_btn = QPushButton("🗑")
        hotkey_btn = QPushButton("⌨")
        play_btn = QPushButton("▶️")
        stop_btn = QPushButton("⏹️")

        add_btn.clicked.connect(self.add_sound)
        del_btn.clicked.connect(self.delete_sound)
        if session == "x11":
            hotkey_btn.clicked.connect(self.assign_hotkey)
        play_btn.clicked.connect(self.play_selected)
        stop_btn.clicked.connect(sd.stop)

        for b in (add_btn, del_btn, hotkey_btn, play_btn, stop_btn):
            b.setFixedHeight(36)
            btns.addWidget(b)

        layout.addLayout(btns)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.setStyleSheet("""
        QWidget {
            background: #121212;
            color: #eaeaea;
            font-size: 14px;
        }
        QPushButton {
            background: #1f1f1f;
            border-radius: 8px;
        }
        QPushButton:hover {
            background: #2c2c2c;
        }
        QListWidget {
            background: #1a1a1a;
            border-radius: 10px;
        }
        """)

    # ---------- LOGIC ----------

    def add_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери звук", "", "Audio (*.wav *.mp3 *.ogg)"
        )
        if not path:
            return
        
        name = os.path.basename(path)
        self.sounds[name] = {"path": path, "key": None}
        self.list.addItem(QListWidgetItem(f"🎵 {name}"))
        self.save_sounds()

    def delete_sound(self):
        item = self.list.currentItem()
        if not item:
            return

        name = item.text().replace("🎵 ", "").split(" [")[0]

        if name in self.hotkey_ids:
            keyboard.remove_hotkey(self.hotkey_ids[name])
            del self.hotkey_ids[name]

        self.sounds.pop(name, None)
        self.list.takeItem(self.list.row(item))
        self.save_sounds()

    def assign_hotkey(self):
        item = self.list.currentItem()
        if not item:
            return

        name = item.text().replace("🎵 ", "").split(" [")[0]

        dlg = HotkeyDialog()
        if dlg.exec() and dlg.key:
            self.sounds[name]["key"] = dlg.key
            item.setText(f"🎵 {name} [{dlg.key}]")
            self.save_sounds()
            self.register_hotkeys()

    def register_hotkeys(self):
        for hid in self.hotkey_ids.values():
            keyboard.remove_hotkey(hid)
        self.hotkey_ids.clear()

        for name, data in self.sounds.items():
            if data["key"]:
                hid = keyboard.add_hotkey(
                    data["key"],
                    lambda n=name: self.play_sound(n)
                )
                self.hotkey_ids[name] = hid

    def play_sound(self, name):
        data, sr = load_audio(self.sounds[name]["path"])
        sd.stop()
        SB_SINK = self.find_sb_sink()
        sd.play(data, device=SB_SINK, blocking=False)

    def play_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        name = item.text().replace("🎵 ", "").split(" [")[0]
        self.play_sound(name)

    def find_sb_sink(self):
        for i, dev in enumerate(sd.query_devices()):
            if "soundboard_internal" in dev["name"].lower():
                return i
        raise RuntimeError("Soundboard sink not found")

    # ---------- SETTINGS ----------

    def load_sounds(self):
        self.list.clear()
        self.sounds.clear()

        size = self.settings.beginReadArray("sounds")
        for i in range(size):
            self.settings.setArrayIndex(i)
            name = self.settings.value("name")
            path = self.settings.value("path")
            key = self.settings.value("key")
            if path and os.path.exists(path):
                self.sounds[name] = {"path": path, "key": key}
                text = f"🎵 {name}"
                if key:
                    text += f" [{key}]"
                self.list.addItem(QListWidgetItem(text))
        self.settings.endArray()

    def save_sounds(self):
        self.settings.beginWriteArray("sounds")
        for i, (name, data) in enumerate(self.sounds.items()):
            self.settings.setArrayIndex(i)
            self.settings.setValue("name", name)
            self.settings.setValue("path", data["path"])
            self.settings.setValue("key", data["key"])
        self.settings.endArray()

    def closeEvent(self, event):
        sd.stop()
        keyboard.clear_all_hotkeys()
        event.accept()


# ---------------- MAIN ----------------

if __name__ == "__main__":
    sb = pactl.SoundboardPulse()
    sb.load()

    app = QApplication(sys.argv)
    window = SoundboardWindow()
    window.show()
    sys.exit(app.exec())