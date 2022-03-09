import typing as t
import functools
from contextlib import ExitStack
import json
import email

from flask import request
from pydantic.fields import ModelField, Undefined
from pydantic.error_wrappers import ErrorWrapper

from flask_dependant.utils import get_dependant, get_body_field, get_parameterless_sub_dependant
from flask_dependant.utils import solve_dependencies
from flask_dependant.models import Dependant
from flask_dependant.exceptions import RequestValidationError, HTTPException
from flask_dependant.exception_handlers import http_exception_handler, request_validation_exception_handler
from flask_dependant import params


class FlaskDependant:
    def __init__(
        self,
        exception_handlers: t.Optional[t.Dict[t.Type[Exception], t.Callable]] = None,
        dependencies: t.Optional[t.Sequence[params.Depends]] = None,
    ):
        self.middlewares: t.List[t.Callable] = []
        self.dependencies = dependencies or []
        self.exception_handlers = exception_handlers or {}
        self.exception_handlers.setdefault(HTTPException, http_exception_handler)
        self.exception_handlers.setdefault(RequestValidationError, request_validation_exception_handler)
        self.middlewares.append(self.chain_exception_handlers())

    def chain_exception_handlers(self) -> t.Callable:
        def wrapper(handler):
            @functools.wraps(handler)
            def inner(*args, **kwargs):
                try:
                    return handler(*args, **kwargs)
                except Exception as exc:
                    for cls in type(exc).__mro__:
                        if cls in self.exception_handlers:
                            return self.exception_handlers[cls](exc)
                    raise exc
            return inner
        return wrapper

    def fork_sub_dependant(self, dependencies: t.Optional[t.Sequence[params.Depends]] = None) -> 'FlaskDependant':
        return FlaskDependant(self.exception_handlers, self.dependencies + (dependencies or []))

    def __call__(self, dependencies: t.Optional[t.Sequence[params.Depends]] = None) -> t.Callable:
        def wrapper(call):
            dependant = get_dependant(call=call)
            _dependencies = self.dependencies + (dependencies or [])
            for depends in _dependencies[::-1]:
                dependant.dependencies.insert(
                    0,
                    get_parameterless_sub_dependant(depends=depends)
                )
            body_field = get_body_field(dependant=dependant)
            return self.build_flask_view_func(get_route_handler(dependant, body_field))
        return wrapper

    def build_flask_view_func(self, view_func: t.Callable) -> t.Callable:
        handler = None
        for middleware in self.middlewares[::-1]:
            handler = middleware(view_func)
        return handler


def get_route_handler(dependant: Dependant, body_field: t.Optional[ModelField]) -> t.Callable:
    is_body_form = body_field and isinstance(body_field.field_info, params.Form)

    @functools.wraps(dependant.call)
    def wrapper(**flask_path_params):
        try:
            body: t.Any = None
            if body_field:
                if is_body_form:
                    body = request.form.to_dict()
                else:
                    body_bytes = request.data
                    if body_bytes:
                        json_body: t.Any = Undefined
                        content_type_value = request.headers.get("content-type")
                        if not content_type_value:
                            json_body = json.loads(request.data)
                        else:
                            message = email.message.Message()
                            message["content-type"] = content_type_value
                            if message.get_content_maintype() == "application":
                                subtype = message.get_content_subtype()
                                if subtype == "json" or subtype.endswith("+json"):
                                    json_body = json.loads(request.data)
                        if json_body != Undefined:
                            body = json_body
                        else:
                            body = body_bytes
        except json.JSONDecodeError as e:
            raise RequestValidationError([ErrorWrapper(e, ("body", e.pos))], body=e.doc)
        except Exception as e:
            raise RequestValidationError([ErrorWrapper(e, ("body",))], body="There was an error parsing the body")
        with ExitStack() as stack:
            solved_result = solve_dependencies(
                request=request,
                dependant=dependant,
                stack=stack,
                is_body_form=is_body_form,
                path_params=flask_path_params,
                body=body,
            )
            values, errors, _ = solved_result
            if errors:
                raise RequestValidationError(errors, body=body)
            res = dependant.call(**values)
        return res
    return wrapper
