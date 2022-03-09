from typing import Sequence, Any, Type

from pydantic.error_wrappers import ValidationError, ErrorList
from pydantic import create_model, BaseModel
from flask import Response


RequestErrorModel: Type[BaseModel] = create_model("Request")


class HTTPException(Exception):
    def __init__(self, resp) -> None:
        self.resp = resp

    # def __repr__(self) -> str:
    #     class_name = self.__class__.__name__
    #     return f"{class_name}(status_code={self.status_code!r}, detail={self.detail!r})"


class RequestValidationError(ValidationError):
    def __init__(self, errors: Sequence[ErrorList], *, body: Any = None) -> None:
        self.body = body
        super().__init__(errors, RequestErrorModel)
