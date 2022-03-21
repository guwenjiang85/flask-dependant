from flask_dependant.response import Response, JsonResponse
from flask_dependant.exceptions import RequestValidationError, HTTPException


def http_exception_handler(exc: HTTPException) -> Response:
    exc.response.set_content(exc.payload)
    return exc.response


def request_validation_exception_handler(
    exc: RequestValidationError
) -> Response:
    resp = exc.response
    if not isinstance(resp, JsonResponse):
        resp.set_content("BAD REQUEST")
    else:
        resp.set_content({"detail": exc.errors()})
    resp.status_code = 422
    return resp
