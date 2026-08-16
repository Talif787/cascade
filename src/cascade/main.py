from __future__ import annotations

import uvicorn

from cascade.infrastructure.config import get_settings
from cascade.presentation.api.app import create_app

settings = get_settings()
app = create_app(settings)


def main() -> None:
    uvicorn.run(
        "cascade.main:app",
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
