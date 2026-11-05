"""Visina sistemskih traka na Androidu (statusna i navigaciona traka).

Od Androida 15 aplikacija se crta preko cele povrsine ekrana, pa sama mora
da ostavi prostor za sistemske trake.
"""

from kivy.logger import Logger
from kivy.utils import platform

SDK_WITH_INSETS_API = 30


def get_system_insets():
    """Vraca (gore, dole) u pikselima.

    Van Androida vraca (0, 0). Na Androidu vraca None kada sistem jos ne daje
    podatke ili kada dodje do greske; pozivalac tada pokusava ponovo kasnije.
    """
    if platform != "android":
        return (0, 0)
    try:
        return _read_android_insets()
    except Exception as error:  # JNI greske ne smeju da sruse aplikaciju
        Logger.warning("TVPG: ne mogu da procitam sistemske trake: %s", error)
        return None


def _read_android_insets():
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    decor_view = activity.getWindow().getDecorView()
    insets = decor_view.getRootWindowInsets()
    if insets is None:
        return None
    sdk = autoclass("android.os.Build$VERSION").SDK_INT
    if sdk >= SDK_WITH_INSETS_API:
        insets_type = autoclass("android.view.WindowInsets$Type")
        bars = insets.getInsets(
            insets_type.systemBars() | insets_type.displayCutout()
        )
        return (int(bars.top), int(bars.bottom))
    return (
        int(insets.getSystemWindowInsetTop()),
        int(insets.getSystemWindowInsetBottom()),
    )
