from __future__ import annotations

import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def create_icon_image(
    color: str = "green", size: tuple[int, int] = (64, 64)
) -> Image.Image:
    """Generates a simple colored circle icon."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, size[0] - 8, size[1] - 8), fill=color)
    return image


class SlouchAppUI:
    def __init__(self, toggle_callback, quit_callback):
        self.toggle_callback = toggle_callback
        self.quit_callback = quit_callback
        self.icon = None
        self.enabled = True

    def _on_toggle(self, icon, item):
        self.enabled = not self.enabled
        self.toggle_callback(self.enabled)
        self.update_icon()

    def _on_quit(self, icon, item):
        self.quit_callback()
        icon.stop()

    def update_icon(self):
        color = "green" if self.enabled else "red"
        if self.icon:
            self.icon.icon = create_icon_image(color)

    def run(self):
        """Starts the system tray icon. Blocks until quit."""
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(
                "Enable/Disable", self._on_toggle, checked=lambda item: self.enabled
            ),
            pystray.MenuItem("Quit", self._on_quit),
        )

        self.icon = pystray.Icon(
            "Slouchless", create_icon_image("green"), "Slouch Detector", menu
        )
        self.icon.run()
