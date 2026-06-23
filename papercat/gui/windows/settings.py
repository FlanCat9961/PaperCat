from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from papercat.gui.controllers.settings import SettingsController
from papercat.gui.i18n import t


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("dialog.settings.title"))
        self.controller: SettingsController | None = None

        self.wallpaper_dir = QLineEdit()
        self.non_kept_limit = QSpinBox()
        self.non_kept_limit.setMinimum(1)
        self.non_kept_limit.setMaximum(100000)
        self.nsfw_enabled = QCheckBox(t("settings.nsfw"))
        self.proxy_enabled = QCheckBox(t("settings.proxy_enabled"))
        self.proxy_url = QLineEdit()
        self.wallhaven_key = QLineEdit()
        self.per_sub_max = QSpinBox()
        self.per_sub_max.setMinimum(1)
        self.per_sub_max.setMaximum(10000)

        form = QFormLayout()
        form.addRow(t("settings.wallpaper_dir"), self.wallpaper_dir)
        form.addRow(t("settings.non_kept_limit"), self.non_kept_limit)
        form.addRow(t("settings.nsfw"), self.nsfw_enabled)
        form.addRow(t("settings.proxy_enabled"), self.proxy_enabled)
        form.addRow(t("settings.proxy_url"), self.proxy_url)
        form.addRow(t("settings.wallhaven_key"), self.wallhaven_key)
        form.addRow(t("settings.per_sub_max"), self.per_sub_max)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def bind(self, controller: SettingsController) -> None:
        self.controller = controller
        config = controller.load()
        self.wallpaper_dir.setText(str(config.wallpaper_dir))
        self.non_kept_limit.setValue(config.non_kept_limit)
        self.nsfw_enabled.setChecked(config.nsfw_master_enabled)
        self.proxy_enabled.setChecked(config.proxy.enabled)
        self.proxy_url.setText(config.proxy.url or "")
        self.wallhaven_key.setText(config.credentials.wallhaven_api_key or "")
        self.per_sub_max.setValue(config.crawl.per_subscription_max)

    def _on_accept(self) -> None:
        if self.controller is None:
            self.accept()
            return
        from pathlib import Path

        config = self.controller.load()
        updated = config.model_copy(
            update={
                "wallpaper_dir": Path(self.wallpaper_dir.text()),
                "non_kept_limit": int(self.non_kept_limit.value()),
                "nsfw_master_enabled": bool(self.nsfw_enabled.isChecked()),
                "proxy": config.proxy.model_copy(
                    update={
                        "enabled": bool(self.proxy_enabled.isChecked()),
                        "url": self.proxy_url.text().strip() or None,
                    }
                ),
                "credentials": config.credentials.model_copy(
                    update={"wallhaven_api_key": self.wallhaven_key.text().strip() or None}
                ),
                "crawl": config.crawl.model_copy(
                    update={"per_subscription_max": int(self.per_sub_max.value())}
                ),
            }
        )
        self.controller.save(updated)
        self.accept()
