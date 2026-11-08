"""Pomocne funkcije za prikaz vremena (srpski tekstovi)."""

def format_age(seconds):
    """Koliko je proslo, npr. "5 min", "2 h 10 min", "3 dana"."""
    minutes = max(0, int(seconds)) // 60
    if minutes < 1:
        return "manje od 1 min"
    if minutes < 60:
        return "%d min" % minutes
    hours, rest = divmod(minutes, 60)
    if hours < 48:
        return "%d h" % hours if rest == 0 else "%d h %d min" % (hours, rest)
    return "%d dana" % (hours // 24)


def format_remaining(seconds):
    """Koliko je ostalo, zaokruzeno na gore na minut, npr. "25 min", "1 h 5 min"."""
    seconds = max(0, int(seconds))
    minutes = (seconds + 59) // 60
    if minutes < 1:
        return "manje od 1 min"
    if minutes < 60:
        return "%d min" % minutes
    hours, rest = divmod(minutes, 60)
    return "%d h" % hours if rest == 0 else "%d h %d min" % (hours, rest)


def day_label(target, today):
    """Oznaka dana u odnosu na danas; None za danas.

    Vraca "juce", "sutra", "prekosutra" ili datum "dd.mm."
    """
    delta = (target - today).days
    if delta == 0:
        return None
    if delta == -1:
        return "juče"
    if delta == 1:
        return "sutra"
    if delta == 2:
        return "prekosutra"
    return target.strftime("%d.%m.")
