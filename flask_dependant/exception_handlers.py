from flask import jsonify
from flask import Request, Response
from flask_dependant.exceptions import RequestValidationError, HTTPException


def http_exception_handler(exc: HTTPException) -> Response:
    # headers = getattr(exc, "headers", None)
    # if headers:
    #     return json(
    #         {"detail": exc.detail}, status_code=exc.status_code, headers=headers
    #     )
    # else:
    return exc.resp


def request_validation_exception_handler(
    exc: RequestValidationError
) -> Response:
    resp = jsonify({
        "detail": exc.errors()
    })
    resp.status_code = 422
    return resp
