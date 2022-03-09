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
        dependencies: Optional[List["Dependant"]] = None,
        # security_schemes: Optional[List[]]
        name: Optional[str] = None,
        call: Optional[Callable[..., Any]] = None,
        request_params_name: Optional[str] = None,
        use_cache: bool = True,
        # path: Optional[str] = None
    ):
        self.path_params = path_params or []
        self.query_params = query_params or []
        self.header_params = header_params or []
        self.cookie_params = cookie_params or []
        self.body_params = body_params or []
        self.dependencies = dependencies or []
        self.request_param_name = request_params_name
        self.name = name
        self.call = call
        self.use_cache = use_cache
        # self.path = path
        self.cache_key = (self.call, )
