from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from synapse_pet.runtime.autonomy import StoredPostIt
from synapse_pet.ui.postit import PostItWindow
from synapse_pet.ui.qt_app import ensure_application


def test_postit_is_owned_non_activating_and_interaction_closes_it():
    app = ensure_application()
    parent = QWidget()
    parent.show()
    now = time.time()
    note = StoredPostIt(1, "alerta", "estressado", now, now + 60, 20, 30)
    callbacks: list[tuple[object, ...]] = []
    window = PostItWindow(
        note, "Uma pausa curta pode ajudar.", quick_dismiss_s=10,
        on_interact=lambda note_id: callbacks.append(("interact", note_id)),
        on_close=lambda *args: callbacks.append(("close", *args)),
        parent=parent, animate=False,
    )
    try:
        assert window.parentWidget() is parent
        assert window.windowFlags() & Qt.WindowType.Tool
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # The centered "Entendi" button sends one interaction and closes the note.
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(222, 104))
        app.processEvents()

        assert callbacks[0] == ("interact", 1)
        assert callbacks[1][0:2] == ("close", 1)
        assert callbacks[1][2] == "interacted"
    finally:
        parent.close()
        app.processEvents()
