import typing as t
import html
import xmltodict

from werkzeug.urls import iri_to_uri

from flask import Response as FlaskResponse
from flask.json import dumps


class Response(FlaskResponse):
    def set_content(self, data: t.Any):
        pass


class JsonResponse(Response):

    def set_content(self, data: dict):
        from flask.globals import current_app
        indent = None
        separators = (",", ":")

        if current_app.config["JSONIFY_PRETTYPRINT_REGULAR"] or current_app.debug:
            indent = 2
            separators = (", ", ": ")

        self.mimetype = current_app.config["JSONIFY_MIMETYPE"]
        self.set_data(f"{dumps(data, indent=indent, separators=separators)}\n")


class PlainTextResponse(Response):
    def set_content(self, data: str):
        self.set_data(data)


class RedirectResponse(Response):
    default_status = 302

    def set_content(self, location: str):
        display_location = html.escape(location)
        location = iri_to_uri(location, safe_conversion=True)
        response = Response(  # type: ignore
        )
        self.set_data(
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
            "<title>Redirecting...</title>\n"
            "<h1>Redirecting...</h1>\n"
            "<p>You should be redirected automatically to target URL: "
            f'<a href="{html.escape(location)}">{display_location}</a>. If'
            " not click the link.",
        )
        self.headers["Location"] = location
        return response


