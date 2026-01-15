from typing import Any

from aiogram_dialog import DialogManager

from src.__version__ import __version__


async def dashboard_main_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for dashboard main page."""
    return {
        "bot_version": __version__,
    }
