"""Keep dependency notices with the experimental desktop bundle."""
import importlib.metadata as metadata
from pathlib import Path
import shutil
import sys

destination = Path(sys.argv[1])
destination.mkdir(parents=True,exist_ok=True)
index = ["# Dependency notices\n", "Each dependency retains its own license. Versions below are those bundled.\n"]
for distribution in sorted(metadata.distributions(),key=lambda d:d.metadata.get("Name","")):
    name = distribution.metadata.get("Name","unknown")
    index.append(f"## {name} {distribution.version}\n")
    for key in ("License-Expression","License","Home-page","Project-URL"):
        for value in distribution.metadata.get_all(key,[]):
            index.append(f"{key}: {value}\n")
    for file in distribution.files or []:
        basename = Path(str(file)).name.lower()
        if basename.startswith(("license","copying","notice")):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                relative = Path(str(file))
                if ".." in relative.parts or relative.is_absolute():
                    continue
                target = destination/name/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
(destination/"INDEX.md").write_text("\n".join(index),encoding="utf-8")
