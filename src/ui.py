import pystray
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from src.settings import settings


def create_icon_image(color="green", size=(64, 64)):
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


def show_popup_process(image_path):
    """
    Helper to run tkinter in a separate process/script context if needed.
    """
    root = tk.Tk()
    root.title("SLOUCH DETECTED!")

    # Load image
    pil_img = Image.open(image_path)
    # Resize for display based on settings
    pil_img.thumbnail(settings.POPUP_THUMBNAIL_SIZE)
    tk_img = ImageTk.PhotoImage(pil_img)

    label = tk.Label(root, image=tk_img)
    label.pack()

    text_label = tk.Label(
        root,
        text="You are slouching! Sit up straight!",
        font=("Helvetica", 16),
        fg="red",
    )
    text_label.pack()

    # Auto focus
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)

    root.mainloop()


def show_slouch_popup(image):
    """
    Spawns a popup to show the user they are slouching.
    We use a temporary file to pass the image to a fresh process/thread safe method
    or just display it if we can.
    """
    import multiprocessing

    # Save image to temp file to pass to process
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        image.save(f, format="JPEG")
        temp_path = f.name

    p = multiprocessing.Process(target=show_popup_process, args=(temp_path,))
    p.start()
    # We can clean up the file later or let OS handle tmp
