"""Run the whole Phase 1 data pipeline: download -> layers -> web export -> previews.

Run from the project folder:  python -m pipeline.run_all
(Downloads are skipped when the file is already in data/raw/.)
"""
from . import download, export_web, layers, previews


def main() -> None:
    download.main([])
    layers.main()
    export_web.main()
    previews.main()


if __name__ == "__main__":
    main()
