from collections.abc import Callable, Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QWidget,
)


BUTTON_COLORS = {
    "create": ("#1D9E75", "#16815F"),
    "edit": ("#BA7517", "#965E12"),
    "delete": ("#D85A30", "#B74724"),
    "reload": ("#185FA5", "#124C84"),
    "reset": ("#5F6B7A", "#48525E"),
    "special": ("#534AB7", "#423A93"),
}


def create_action_button(
    text: str,
    role: str,
    callback: Callable,
    parent: QWidget | None = None,
) -> QPushButton:
    """Create one consistently styled action button."""
    if role not in BUTTON_COLORS:
        raise ValueError(f"Vai trò nút không hợp lệ: {role}")

    normal_color, hover_color = BUTTON_COLORS[role]

    button = QPushButton(text, parent)
    button.setMinimumHeight(34)
    button.setCursor(Qt.PointingHandCursor)
    button.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {normal_color};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0 14px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
        QPushButton:pressed {{
            padding-top: 1px;
        }}
        QPushButton:disabled {{
            background-color: #B8BDC5;
            color: #F2F2F2;
        }}
        """
    )
    button.clicked.connect(callback)
    return button


def create_action_bar(
    actions: Iterable[tuple[str, str, str, Callable]],
) -> tuple[QHBoxLayout, dict[str, QPushButton]]:
    """
    Build an action bar and return its buttons by key.

    Each action is ``(key, display_text, role, callback)``.
    """
    layout = QHBoxLayout()
    layout.setSpacing(8)
    buttons: dict[str, QPushButton] = {}

    for key, text, role, callback in actions:
        if key in buttons:
            raise ValueError(f"Trùng khóa nút: {key}")

        button = create_action_button(text, role, callback)
        buttons[key] = button
        layout.addWidget(button)

    layout.addStretch()
    return layout, buttons


def create_two_column_form(parent: QWidget) -> QGridLayout:
    """Create a balanced two-column data-entry form."""
    layout = QGridLayout(parent)
    layout.setHorizontalSpacing(16)
    layout.setVerticalSpacing(10)
    layout.setContentsMargins(12, 14, 12, 12)
    layout.setColumnStretch(0, 0)
    layout.setColumnStretch(1, 1)
    layout.setColumnStretch(2, 0)
    layout.setColumnStretch(3, 1)
    return layout


def add_form_field(
    layout: QGridLayout,
    row: int,
    pair: int,
    label_text: str,
    widget: QWidget,
) -> QLabel:
    """Add a labelled field to the left (0) or right (1) form pair."""
    if pair not in (0, 1):
        raise ValueError("pair chỉ được là 0 hoặc 1")

    label_column = pair * 2
    field_column = label_column + 1
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.addWidget(label, row, label_column)
    layout.addWidget(widget, row, field_column)
    return label


def create_data_table(
    headers: list[str],
    stretch_columns: tuple[int, ...] = (),
    hidden_columns: tuple[int, ...] = (),
) -> QTableWidget:
    """Create a read-only table whose chosen text columns share free space."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(70)

    for column in range(len(headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

    for column in stretch_columns:
        if 0 <= column < len(headers):
            header.setSectionResizeMode(column, QHeaderView.Stretch)

    for column in hidden_columns:
        if 0 <= column < len(headers):
            table.setColumnHidden(column, True)

    return table
