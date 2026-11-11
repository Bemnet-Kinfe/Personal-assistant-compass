"""Small helpers shared by views, services and templates."""


def fmt_minutes(m):
    m = int(round(m or 0))
    if m < 60:
        return f"{m}m"
    h, r = divmod(m, 60)
    return f"{h}h {r}m" if r else f"{h}h"
