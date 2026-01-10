from typing import TYPE_CHECKING, Annotated, NewType, TypeAlias, Union

from aiogram.types import (
    BufferedInputFile,
    ForceReply,
    FSInputFile,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from pydantic import PlainValidator
from remnapy.models import UserResponseDto
from remnapy.models.webhook import UserDto as UserWebhookDto

from src.core.enums import Locale, SystemNotificationType, UserNotificationType

if TYPE_CHECKING:
    ListStr: TypeAlias = list[str]
    ListLocale: TypeAlias = list[Locale]
else:
    ListStr = NewType("ListStr", list[str])
    ListLocale = NewType("ListLocale", list[Locale])

AnyInputFile: TypeAlias = Union[BufferedInputFile, FSInputFile]

AnyKeyboard: TypeAlias = Union[
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ForceReply,
]

AnyNotification: TypeAlias = Union[SystemNotificationType, UserNotificationType]

RemnaUserDto: TypeAlias = Union[UserWebhookDto, UserResponseDto]  # UserWebhookDto without url

def _parse_string_list(x):
    if isinstance(x, list):
        return [s.strip() for s in x]
    return [s.strip() for s in x.split(",")]

def _parse_locale_list(x):
    if isinstance(x, list):
        return [Locale(loc.strip()) if isinstance(loc, str) else loc for loc in x]
    return [Locale(loc.strip()) for loc in x.split(",")]

StringList: TypeAlias = Annotated[
    ListStr, PlainValidator(_parse_string_list)
]
LocaleList: TypeAlias = Annotated[
    ListLocale, PlainValidator(func=_parse_locale_list)
]
