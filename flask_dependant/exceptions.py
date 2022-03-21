from typing import Sequence, Any, Type, Optional

from pydantic.error_wrappers import ValidationError, ErrorList
from pydantic import create_model, BaseModel
from flask_dependant.response import Response


RequestErrorModel: Type[BaseModel] = create_model("Request")


class HTTPException(Exception):
    def __init__(self, payload: Any) -> None:
        self.response: Optional[Response] = None
        self.payload = payload

    # def __repr__(self) -> str:
    #     class_name = self.__class__.__name__
    #     return f"{class_name}(status_code={self.status_code!r}, detail={self.detail!r})"


class RequestValidationError(ValidationError):
    def __init__(self, errors: Sequence[ErrorList], *, response: Response, body: Any = None, ) -> None:
        self.response = response
        self.body = body
        super().__init__(errors, RequestErrorModel)
