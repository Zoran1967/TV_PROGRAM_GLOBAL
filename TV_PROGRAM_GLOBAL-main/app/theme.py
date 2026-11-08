"""Boje tema. Format: RGBA, vrednosti 0-1.

Tamna tema: tamno plava i zlatna. Svetla tema: svetla pozadina i tamnija zlatna (da tekst
ostane citljiv). Kljucevi su isti u obe palete jer ih koristi main.kv.
"""

PALETTES = {
    "dark": {
        "navy": [0.04, 0.07, 0.15, 1],
        "navy_light": [0.08, 0.12, 0.24, 1],
        "gold": [0.85, 0.70, 0.25, 1],
        "text_muted": [0.72, 0.75, 0.82, 1],
    },
    "light": {
        "navy": [0.96, 0.97, 0.99, 1],
        "navy_light": [0.88, 0.91, 0.96, 1],
        "gold": [0.48, 0.32, 0.00, 1],
        "text_muted": [0.28, 0.32, 0.40, 1],
    },
}

# Kivy/KivyMD naziv teme za svaku paletu
THEME_STYLES = {"dark": "Dark", "light": "Light"}

DEFAULT_THEME = "dark"
COLORS = PALETTES[DEFAULT_THEME]
