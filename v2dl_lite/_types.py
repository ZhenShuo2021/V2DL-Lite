from pathlib import Path
from typing import Literal, TypeAlias

PathType = str | Path
Dl_Status: TypeAlias = tuple[bool, str, str]
Opt_Dict_Str: TypeAlias = dict[str, str] | None
Valid_Session = Literal["curl", "httpx", "primp"]
