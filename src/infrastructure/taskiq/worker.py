from typing import Any

from dishka.integrations.aiogram import setup_dishka as setup_aiogram_dishka
from dishka.integrations.taskiq import setup_dishka as setup_taskiq_dishka
from taskiq import TaskiqMiddleware
from taskiq_redis import RedisStreamBroker

from src.bot.dispatcher import create_bg_manager_factory, create_dispatcher, setup_dispatcher
from src.core.config import AppConfig
from src.core.logger import setup_logger
from src.infrastructure.di import create_container
from src.infrastructure.taskiq.init import init as init_consumer_group

from .broker import broker


class DishkaParamsFilterMiddleware(TaskiqMiddleware):
    """Middleware для фильтрации параметров dishka из task_hints.
    
    Это необходимо потому что dishka добавляет параметр dishka_container в сигнатуру,
    но taskiq пытается его десериализовать через Pydantic, что приводит к ошибке.
    Dishka middleware сам обработает инжекцию зависимостей.
    """
    
    async def startup(self) -> None:
        """При старте очищаем task_hints от dishka параметров."""
        if hasattr(self.broker, 'task_hints'):
            # Удаляем dishka_container из hints для всех задач
            filtered_hints: dict[str, dict[str, Any]] = {}
            for task_name, hints in self.broker.task_hints.items():
                filtered_hints[task_name] = {
                    key: value for key, value in hints.items()
                    if key != 'dishka_container'
                }
            self.broker.task_hints = filtered_hints


def worker() -> RedisStreamBroker:
    setup_logger()

    # Initialize consumer group before starting workers
    init_consumer_group()

    config = AppConfig.get()
    dispatcher = create_dispatcher(config=config)
    bg_manager_factory = create_bg_manager_factory(dispatcher=dispatcher)
    setup_dispatcher(dispatcher)
    container = create_container(config=config, bg_manager_factory=bg_manager_factory)

    setup_taskiq_dishka(container=container, broker=broker)
    setup_aiogram_dishka(container=container, router=dispatcher, auto_inject=True)
    
    # Добавляем middleware для фильтрации dishka параметров из task_hints
    broker.add_middlewares(DishkaParamsFilterMiddleware())

    return broker
