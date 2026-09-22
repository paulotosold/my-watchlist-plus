"""Shared normalization for the discrete poster density choices."""


def normalize_posters_per_row(value, options):
    """Choose the nearest supported density, preferring fewer columns on ties."""
    value = int(value)
    return min(options, key=lambda option: (abs(option - value), option))
