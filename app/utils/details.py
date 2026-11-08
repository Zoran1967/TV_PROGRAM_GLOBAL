"""Tekst ekrana sa detaljima emisije. Cista logika (bez Kivy-ja), da se lako testira.

Prikazuje se samo ono sto izvor stvarno daje; polje koje nedostaje se izostavlja.
"""

from app.utils.programme_kind import KIND_FILM, KIND_SERIES, programme_kind

LIST_SEPARATOR = ", "


def _duration_minutes(entry):
    if entry.end is None:
        return None
    minutes = int((entry.end - entry.start).total_seconds() // 60)
    return minutes if minutes > 0 else None


def _duration_text(translate, minutes):
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return translate("detail_duration_minutes").format(m=rest)
    if rest == 0:
        return translate("detail_duration_hours").format(h=hours)
    return translate("detail_duration_hours_minutes").format(h=hours, m=rest)


def _episode_text(translate, programme):
    season, episode, total = programme.season, programme.episode, programme.episode_total
    if season is not None and episode is not None:
        text = translate("detail_season_episode").format(season=season, episode=episode)
    elif episode is not None:
        text = translate("detail_episode_only").format(episode=episode)
    elif season is not None:
        text = translate("detail_season_only").format(season=season)
    else:
        return None
    if total and episode is not None:
        text = "%s %s" % (text, translate("detail_of_total").format(total=total))
    return text


def _other_genres(programme):
    """Zanrovi kao lista (bez ponavljanja); kategorija iz stare kesirane emisije je jedini zanr."""
    names = list(programme.genres or ())
    if programme.category and programme.category not in names:
        names.insert(0, programme.category)
    return names


def build_details(translate, entry, when_text, channel_name=""):
    """Vraca (naslov, oznaka vrste, tekst) za dijalog sa detaljima.

    translate: funkcija kljuc -> tekst (app.t). when_text: vec formatirano vreme (npr. \"19:30-20:00\").
    """
    programme = entry.programme
    kind = programme_kind(programme)

    kind_key = {KIND_FILM: "detail_kind_film", KIND_SERIES: "detail_kind_series"}.get(
        kind, "detail_kind_other")
    kind_label = translate(kind_key)

    head = [kind_label]
    if programme is not None and kind == KIND_FILM and programme.year:
        head.append(str(programme.year))
    minutes = _duration_minutes(entry)
    if minutes is not None:
        head.append(_duration_text(translate, minutes))
    if programme is not None and programme.age_rating:
        head.append(translate("detail_age").format(value=programme.age_rating))

    lines = [" \u00b7 ".join(head)]

    if programme is not None and kind == KIND_SERIES:
        episode = _episode_text(translate, programme)
        if episode:
            lines.append(episode)
        if programme.subtitle:
            lines.append(translate("detail_episode_title").format(subtitle=programme.subtitle))
        if programme.year:
            lines.append(translate("detail_year").format(year=programme.year))
    elif programme is not None and programme.subtitle:
        lines.append(translate("detail_subtitle").format(subtitle=programme.subtitle))

    when = when_text if not channel_name else "%s \u00b7 %s" % (when_text, channel_name)
    lines.append(translate("detail_when").format(when=when))

    if programme is not None:
        genres = _other_genres(programme)
        if genres:
            lines.append(translate("detail_genre").format(value=LIST_SEPARATOR.join(genres)))
        if programme.directors:
            lines.append(translate("detail_director").format(value=LIST_SEPARATOR.join(programme.directors)))
        if programme.actors:
            lines.append(translate("detail_cast").format(value=LIST_SEPARATOR.join(programme.actors)))
        if programme.countries:
            lines.append(translate("detail_country").format(value=LIST_SEPARATOR.join(programme.countries)))

    lines.append("")
    if entry.description:
        lines.append(entry.description)
    else:
        lines.append(translate("detail_no_description"))
    return entry.title, kind_label, "\n".join(lines)
