from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from papercat.core.sources import DEFAULT_REGISTRY
from papercat.core.subscription import Subscription
from papercat.core.types import AspectRatio, NsfwLevel, Resolution
from papercat.gui.i18n import t

if TYPE_CHECKING:
    from papercat.gui.app import AppControllers


_DEFAULT_RESOLUTIONS = [
    Resolution(1920, 1080),
    Resolution(2560, 1440),
    Resolution(3840, 2160),
]


class SubscriptionEditorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("dialog.subscription.title"))
        self._editing_id: int | None = None

        self.name = QLineEdit()
        self.source = QComboBox()
        self.include_tags = QLineEdit()
        self.exclude_tags = QLineEdit()
        self.resolution = QComboBox()
        self.aspect_ratio = QLineEdit("16:9")
        self.allow_nsfw = QCheckBox(t("settings.nsfw"))
        self.crawl_strategy = QComboBox()
        self.max_scan_pages = QSpinBox()
        self.max_scan_candidates = QSpinBox()

        self.crawl_strategy.addItem(t("subscription.strategy.latest_fill"), "latest_fill")
        self.crawl_strategy.addItem(
            t("subscription.strategy.incremental_strict"), "incremental_strict"
        )
        self.crawl_strategy.addItem(t("subscription.strategy.random"), "random")
        self.max_scan_pages.setRange(1, 1000)
        self.max_scan_pages.setValue(5)
        self.max_scan_candidates.setRange(1, 100000)
        self.max_scan_candidates.setValue(200)

        for src in DEFAULT_REGISTRY.available():
            self.source.addItem(src.display_name, src.id)
        for res in _DEFAULT_RESOLUTIONS:
            self.resolution.addItem(str(res), (res.width, res.height))

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Source", self.source)
        form.addRow("Include", self.include_tags)
        form.addRow("Exclude", self.exclude_tags)
        form.addRow("Resolution", self.resolution)
        form.addRow("Aspect", self.aspect_ratio)
        form.addRow("NSFW", self.allow_nsfw)
        form.addRow(t("subscription.strategy"), self.crawl_strategy)
        form.addRow(t("subscription.max_scan_pages"), self.max_scan_pages)
        form.addRow(t("subscription.max_scan_candidates"), self.max_scan_candidates)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def bind(
        self,
        controllers: AppControllers,
        subscription: Subscription | None = None,
    ) -> None:
        try:
            for res in controllers.monitor_detector.all_resolutions(
                controllers.config.user_resolutions
            ):
                if (res.width, res.height) not in [
                    self.resolution.itemData(i) for i in range(self.resolution.count())
                ]:
                    self.resolution.addItem(str(res), (res.width, res.height))
        except Exception:
            pass

        if subscription is None:
            return
        self._editing_id = subscription.id
        self.name.setText(subscription.name)
        idx = self.source.findData(subscription.source)
        if idx >= 0:
            self.source.setCurrentIndex(idx)
        self.include_tags.setText(", ".join(subscription.include_tags))
        self.exclude_tags.setText(", ".join(subscription.exclude_tags))
        res_key = (subscription.resolution.width, subscription.resolution.height)
        res_idx = self.resolution.findData(res_key)
        if res_idx < 0:
            self.resolution.addItem(str(subscription.resolution), res_key)
            res_idx = self.resolution.count() - 1
        self.resolution.setCurrentIndex(res_idx)
        if subscription.aspect_ratio is not None:
            self.aspect_ratio.setText(
                f"{subscription.aspect_ratio.width}:{subscription.aspect_ratio.height}"
            )
        self.allow_nsfw.setChecked(subscription.nsfw_level != NsfwLevel.SFW)
        strategy_idx = self.crawl_strategy.findData(subscription.crawl_strategy)
        if strategy_idx >= 0:
            self.crawl_strategy.setCurrentIndex(strategy_idx)
        self.max_scan_pages.setValue(subscription.max_scan_pages)
        self.max_scan_candidates.setValue(subscription.max_scan_candidates)

    def build_subscription(self) -> Subscription | None:
        try:
            res_data = self.resolution.currentData()
            if not res_data:
                raise ValueError("resolution required")
            resolution = Resolution(int(res_data[0]), int(res_data[1]))

            aspect_text = self.aspect_ratio.text().strip()
            aspect: AspectRatio | None = None
            if aspect_text:
                parts = aspect_text.replace("x", ":").split(":")
                if len(parts) != 2:
                    raise ValueError("aspect ratio must be like 16:9")
                aspect = AspectRatio(int(parts[0]), int(parts[1]))

            return Subscription(
                id=self._editing_id if self._editing_id is not None else 0,
                name=self.name.text().strip() or "untitled",
                source=str(self.source.currentData()),
                include_tags=_split_tags(self.include_tags.text()),
                exclude_tags=_split_tags(self.exclude_tags.text()),
                resolution=resolution,
                aspect_ratio=aspect,
                nsfw_level=NsfwLevel.NSFW if self.allow_nsfw.isChecked() else NsfwLevel.SFW,
                crawl_strategy=str(self.crawl_strategy.currentData()),
                max_scan_pages=self.max_scan_pages.value(),
                max_scan_candidates=self.max_scan_candidates.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, t("dialog.error.title"), str(exc))
            return None


def _split_tags(text: str) -> list[str]:
    return [tag.strip() for tag in text.replace(";", ",").split(",") if tag.strip()]
