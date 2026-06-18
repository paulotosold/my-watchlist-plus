from dataclasses import dataclass, field

@dataclass

class MediaSession:

    filter_parameters: dict = field(default_factory=dict)

    media_list: list = field(default_factory=list)

    next_media_index: int = 0