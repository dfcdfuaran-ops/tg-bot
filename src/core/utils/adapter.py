from typing import Any, Optional, Type, TypeVar

from aiogram_dialog import DialogManager
from loguru import logger
from pydantic import ValidationError

from src.infrastructure.database.models.dto import BaseDto

DtoModel = TypeVar("DtoModel", bound="BaseDto")


class DialogDataAdapter:
    def __init__(self, dialog_manager: DialogManager) -> None:
        self.dialog_manager = dialog_manager

    def load(self, model_cls: Type[DtoModel]) -> Optional[DtoModel]:
        key = model_cls.__name__.lower()
        raw = self.dialog_manager.dialog_data.get(key)
        logger.info(f"🔍 Loading model '{key}' with data keys: {list(raw.keys()) if isinstance(raw, dict) else 'None'}")

        if raw is None:
            return None

        try:
            return model_cls.model_validate(raw)
        except ValidationError:
            return None

    def save(self, model: DtoModel) -> dict[str, Any]:
        key = model.__class__.__name__.lower()
        data = model.model_dump()
        try:
            self.dialog_manager.dialog_data[key] = data
            logger.info(f"🔍 Model '{key}' data saved with {len(data)} fields")
        except Exception as exception:
            logger.error(f"Failed data save for model '{key}'. Error: {exception}")
        return data
