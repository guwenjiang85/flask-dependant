from typing import Optional, List, Callable, Any

from pydantic.fields import ModelField


class Dependant:
    def __init__(
        self,
        *,
        path_params: Optional[List[ModelField]] = None,
        query_params: Optional[List[ModelField]] = None,
        header_params: Optional[List[ModelField]] = None,
        cookie_params: Optional[List[ModelField]] = None,
        body_params: Optional[List[ModelField]] = None,
        response_param_name: Optional[str] = None,
        dependencies: Optional[List["Dependant"]] = None,
        name: Optional[str] = None,
        call: Optional[Callable[..., Any]] = None,
        use_cache: bool = True,
    ):
        self.path_params = path_params or []
        self.query_params = query_params or []
        self.header_params = header_params or []
        self.cookie_params = cookie_params or []
        self.body_params = body_params or []
        self.dependencies = dependencies or []
        self.response_param_name = response_param_name
        self.name = name
        self.call = call
        self.use_cache = use_cache
        self.cache_key = (self.call, )
