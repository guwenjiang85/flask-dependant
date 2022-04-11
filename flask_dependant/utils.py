from typing import (
    Callable,
    Optional,
    Any,
    Dict,
    List,
    Type,
    Tuple,
    Union,
    Sequence,
    cast,
)
import inspect
import functools
import dataclasses
from contextlib import ExitStack, contextmanager
from copy import deepcopy

from flask.wrappers import Request
from pydantic.typing import ForwardRef, evaluate_forwardref
from pydantic.fields import (
    Required,
    FieldInfo,
    ModelField,
    UndefinedType,
    SHAPE_SINGLETON,
    SHAPE_LIST,
    SHAPE_SET,
    SHAPE_TUPLE,
    SHAPE_SEQUENCE,
    SHAPE_TUPLE_ELLIPSIS,
)
from pydantic.utils import lenient_issubclass
from pydantic.schema import get_annotation_from_field_info
from pydantic.class_validators import Validator
from pydantic.config import BaseConfig
from pydantic.error_wrappers import ErrorWrapper
from pydantic.errors import MissingError
from pydantic import BaseModel, create_model

from flask_dependant.models import Dependant
from flask_dependant.response import Response
from flask_dependant import params

sequence_shapes = {
    SHAPE_LIST,
    SHAPE_SET,
    SHAPE_TUPLE,
    SHAPE_SEQUENCE,
    SHAPE_TUPLE_ELLIPSIS,
}

sequence_types = (list, set, tuple)


multipart_not_installed_error = (
    'Form data requires "python-multipart" to be installed. \n'
    'You can install "python-multipart" with: \n\n'
    "pip install python-multipart\n"
)


multipart_incorrect_install_error = (
    'Form data requires "python-multipart" to be installed. '
    'It seems you installed "multipart" instead. \n'
    'You can remove "multipart" with: \n\n'
    "pip uninstall multipart\n\n"
    'And then install "python-multipart" with: \n\n'
    "pip install python-multipart\n"
)


def is_gen_callable(call: Callable[..., Any]) -> bool:
    if inspect.isgeneratorfunction(call):
        return True
    call = getattr(call, "__call__", None)
    return inspect.isgeneratorfunction(call)


def solve_generator(
    *, call: Callable[..., Any], stack: ExitStack, sub_values: Dict[str, Any]
) -> Any:
    return stack.enter_context(contextmanager(call)(**sub_values))


def check_file_field(field: ModelField) -> None:
    """check form data python packaages"""
    field_info = field.field_info
    if isinstance(field_info, params.Form):
        try:
            # __version__ is available in both multiparts, and can be mocked
            from multipart import __version__  # type: ignore

            assert __version__
            try:
                # parse_options_header is only available in the right multipart
                from multipart.multipart import parse_options_header  # type: ignore

                assert parse_options_header
            except ImportError:
                # logger.error(multipart_incorrect_install_error)
                raise RuntimeError(multipart_incorrect_install_error)
        except ImportError:
            # logger.error(multipart_not_installed_error)
            raise RuntimeError(multipart_not_installed_error)


def create_response_field(
    name: str,
    type_: Type[Any],
    class_validators: Optional[Dict[str, Validator]] = None,
    default: Optional[Any] = None,
    required: Union[bool, UndefinedType] = False,
    model_config: Type[BaseConfig] = BaseConfig,
    field_info: Optional[FieldInfo] = None,
    alias: Optional[str] = None
) -> ModelField:
    class_validators = class_validators or {}
    field_info = field_info or FieldInfo(None)

    response_field = functools.partial(
        ModelField,
        name=name,
        type_=type_,
        class_validators=class_validators,
        default=default,
        required=required,
        model_config=model_config,
        alias=alias
    )
    try:
        return response_field(field_info=field_info)
    except RuntimeError:
        raise Exception(
            f"Invalid args for response field! Hint: check that {type_} is a valid pydantic field type"
        )


def is_scalar_field(field: ModelField) -> bool:
    field_info = field.field_info
    if not (
        field.shape == SHAPE_SINGLETON
        and not lenient_issubclass(field.type_, BaseModel)
        and not lenient_issubclass(field.type_, sequence_types + (dict,))
        and not dataclasses.is_dataclass(field.type_)
        and not isinstance(field_info, params.Body)
    ):
        return False
    if field.sub_fields:
        if not all(is_scalar_field(field) for f in field.sub_fields):
            return False
    return True


def is_scalar_sequence_field(field: ModelField) -> bool:
    if (field.shape in sequence_shapes) and not lenient_issubclass(
        field.type_, BaseModel
    ):
        if field.sub_fields is not None:
            for sub_field in field.sub_fields:
                if not is_scalar_field(sub_field):
                    return False
        return True
    if lenient_issubclass(field.type_, sequence_types):
        return True
    return False


def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=get_typed_annotation(param, globalns)
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(typed_params)
    return typed_signature


def get_param_sub_dependant(
    *, param: inspect.Parameter
):
    depends: params.Depends = param.default
    if depends.dependency:
        dependency = depends.dependency
    else:
        dependency = param.annotation
    return get_sub_dependant(
        depends=depends,
        dependency=dependency,
        name=param.name,
    )


def get_sub_dependant(
    *,
    depends: params.Depends,
    dependency: Callable[..., Any],
    name: Optional[str] = None
) -> Dependant:
    sub_dependant = get_dependant(
        call=dependency,
        name=name,
        use_cache=depends.use_cache
    )
    return sub_dependant


CacheKey = Tuple[Optional[Callable[..., Any]], Tuple[str, ...]]


def get_flat_dependant(
    dependant: Dependant,
    *,
    skip_repeats: bool = False,
    visited: Optional[List[CacheKey]] = None,
):
    """将dependant和其子dependant的信息平整化"""
    if visited is None:
        visited = []
    visited.append(dependant.cache_key)

    flat_dependant = Dependant(
        path_params=dependant.path_params.copy(),
        query_params=dependant.query_params.copy(),
        header_params=dependant.header_params.copy(),
        cookie_params=dependant.cookie_params.copy(),
        body_params=dependant.body_params.copy(),
        use_cache=dependant.use_cache,
        # path=dependant.path,
    )
    for sub_dependant in dependant.dependencies:
        if skip_repeats and sub_dependant.cache_key in visited:
            continue
        flat_sub = get_flat_dependant(
            sub_dependant, skip_repeats=skip_repeats, visited=visited
        )
        flat_dependant.path_params.extend(flat_sub.path_params)
        flat_dependant.query_params.extend(flat_sub.query_params)
        flat_dependant.header_params.extend(flat_sub.header_params)
        flat_dependant.cookie_params.extend(flat_sub.cookie_params)
        flat_dependant.body_params.extend(flat_sub.body_params)
    return flat_dependant


def add_non_field_param_to_dependency(
    *, param: inspect.Parameter, dependant: Dependant
) -> Optional[bool]:
    """判断是否自定义的函数签名"""
    if lenient_issubclass(param.annotation, Response):
        dependant.response_param_name = param.name
        return True
    return None


def add_param_to_fields(*, field: ModelField, dependant: Dependant) -> None:
    field_info = cast(params.Param, field.field_info)
    if field_info.in_ == params.ParamTypes.path:
        dependant.path_params.append(field)
    elif field_info.in_ == params.ParamTypes.query:
        dependant.query_params.append(field)
    elif field_info.in_ == params.ParamTypes.header:
        dependant.header_params.append(field)
    else:
        assert (
            field_info.in_ == params.ParamTypes.cookie
        ), f"non-body parameters must be in path, query, header or cookie: {field.name}"
        dependant.cookie_params.append(field)


def get_param_field(
    *,
    param: inspect.Parameter,
    param_name: str,
    default_field_info: Type[params.Param] = params.Path,
    force_type: Optional[params.ParamTypes] = None,
    ignore_default: bool = False
) -> ModelField:
    default_value = Required
    had_schema = False
    # 获取默认值
    if not param.default == param.empty and ignore_default is False:
        default_value = param.default
    # 获取参数的字段信息，
    # 如果有默认值，根据默认值的类型，如果指定了，就用指定的，
    # 不是就使用default_field_info构建 a: int = 1
    if isinstance(default_value, FieldInfo):
        had_schema = True
        field_info = default_value
        # 真实的默认值
        default_value = field_info.default
        if (
            isinstance(field_info, params.Param)
            and getattr(field_info, "in_", None) is None
        ):
            field_info.in_ = default_field_info.in_
        if force_type:
            field_info.in_ = force_type
    else:
        field_info = default_field_info(default_value)
    required = default_value == Required
    annotation: Any = Any
    if not param.annotation == param.empty:
        annotation = param.annotation
    annotation = get_annotation_from_field_info(annotation, field_info, param_name)
    if not field_info.alias and getattr(field_info, "convert_underscores", None):
        alias = param.name.replace("_", "-")
    else:
        alias = field_info.alias or param.name
    # flask header首字母会自动大写
    if isinstance(field_info, params.Header) and alias:
        alias = alias[0].upper() + alias[1:]

    field = create_response_field(
        name=param.name,
        type_=annotation,
        default=None if required else default_value,
        alias=alias,
        required=required,
        field_info=field_info
    )
    field.required = required
    if not had_schema and not is_scalar_field(field=field):
        field.field_info = params.Body(field_info.default)
    # todo uploadfile
    return field


def get_typed_annotation(param: inspect.Parameter, globalns: Dict[str, Any]) -> Any:
    """if annotation is str, revert str to scalar type; ex: s: 'int' -> s : int"""
    annotation = param.annotation
    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        annotation = evaluate_forwardref(annotation, globalns, globalns)
    return annotation


def get_dependant(
    *,
    call: Callable,
    name: Optional[str] = None,
    use_cache: bool = True
):
    # 获取函数的入参签名
    endpoint_signature = get_typed_signature(call)
    signature_params = endpoint_signature.parameters
    # dependant = Dependant(call=call, name=name, path=path, use_cache=use_cache)
    dependant = Dependant(call=call, name=name, use_cache=use_cache)
    for param_name, param in signature_params.items():
        # 嵌套依赖注入
        if isinstance(param.default, params.Depends):
            sub_dependant = get_param_sub_dependant(
                param=param
            )
            dependant.dependencies.append(sub_dependant)
            continue

        if add_non_field_param_to_dependency(param=param, dependant=dependant):
            continue

        if param.default == param.empty:
            param_field = get_param_field(
                param=param,
                param_name=param_name,
                default_field_info=params.Path,
                force_type=params.ParamTypes.path,
                ignore_default=not isinstance(param.default, params.Path)
            )
            assert is_scalar_field(
                field=param_field
            ), "Path params must be of one of the supported types"
        else:
            param_field = get_param_field(
                param=param, default_field_info=params.Path, param_name=param_name
            )
        if isinstance(param_field.default, params.Path):
            add_param_to_fields(field=param_field, dependant=dependant)
        # for param_name in
        elif is_scalar_field(field=param_field):
            add_param_to_fields(field=param_field, dependant=dependant)
        elif isinstance(
            param.default, (params.Query, params.Header)
        ) and is_scalar_sequence_field(field=param_field):
            add_param_to_fields(field=param_field, dependant=dependant)
        else:
            field_info = param_field.field_info
            assert isinstance(
                field_info, params.Body
            ), f"Param: {param_field.name} can only be a request body, using Body(...)"
            dependant.body_params.append(param_field)
    return dependant


def get_missing_field_error(loc: Tuple[str, ...]) -> ErrorWrapper:
    missing_field_error = ErrorWrapper(MissingError(), loc=loc)
    return missing_field_error


def get_body_field(*, dependant: Dependant) -> Optional[ModelField]:
    flat_dependant = get_flat_dependant(dependant)
    if not flat_dependant.body_params:
        return None
    first_param = flat_dependant.body_params[0]
    field_info = first_param.field_info
    embed = getattr(field_info, "embed", None)
    body_param_names_set = {param.name for param in flat_dependant.body_params}
    # todo dependant 和subdependant 参数同名
    if len(body_param_names_set) == 1 and not embed:
        check_file_field(first_param)
        return first_param
    # todo why
    for param in flat_dependant.body_params:
        setattr(param.field_info, "embed", True)
    model_name = "Body_" + ""
    # todo name
    # model_name = "Body_" + dependant.name
    BodyModel: Type[BaseModel] = create_model(model_name)
    for f in flat_dependant.body_params:
        BodyModel.__fields__[f.name] = f
    required = any(True for f in flat_dependant.body_params if f.required)

    BodyFieldInfo_kwargs: Dict[str, Any] = dict(default=None)
    if any(isinstance(f.field_info, params.File) for f in flat_dependant.body_params):
        BodyFieldInfo: Type[params.Body] = params.File
    elif any(isinstance(f.field_info, params.Form) for f in flat_dependant.body_params):
        BodyFieldInfo = params.Form
    else:
        BodyFieldInfo = params.Body

        body_param_media_types = [
            getattr(f.field_info, "media_type")
            for f in flat_dependant.body_params
            if isinstance(f.field_info, params.Body)
        ]
        if len(set(body_param_media_types)) == 1:
            BodyFieldInfo_kwargs["media_type"] = body_param_media_types
    final_field = create_response_field(
        name="body",
        type_=BodyModel,
        required=required,
        alias="body",
        field_info=BodyFieldInfo(**BodyFieldInfo_kwargs)
    )
    check_file_field(final_field)
    return final_field


def get_parameterless_sub_dependant(*, depends: params.Depends) -> Dependant:
    assert callable(
        depends.dependency
    ), "A parameter-less dependency must have a callable dependency"
    return get_sub_dependant(depends=depends, dependency=depends.dependency)


def solve_dependencies(
    *,
    request: Request,
    response: Response,
    dependant: Dependant,
    stack: ExitStack,
    is_body_form: bool,
    path_params: dict,
    body: Optional[Dict[str, Any]] = None,
    dependency_cache: Optional[Dict[Tuple[Callable[..., Any], Tuple[str]], Any]] = None,
) -> Tuple[
    Dict[str, Any],
    List[ErrorWrapper],
    Dict[Tuple[Callable[..., Any], Tuple[str]], Any],
]:
    values: Dict[str, Any] = {}
    errors: List[ErrorWrapper] = []
    dependency_cache = dependency_cache or {}
    sub_dependant: Dependant
    for sub_dependant in dependant.dependencies:
        sub_dependant.call = cast(Callable[..., Any], sub_dependant.call)
        sub_dependant.cache_key = cast(
            Tuple[Callable[..., Any], Tuple[str]], sub_dependant.cache_key
        )
        call = sub_dependant.call
        use_sub_dependant = sub_dependant

        solved_result = solve_dependencies(
            request=request,
            response=response,
            is_body_form=is_body_form,
            path_params=path_params,
            dependant=use_sub_dependant,
            stack=stack,
            body=body,
            dependency_cache=dependency_cache
        )
        (
            sub_values,
            sub_errors,
            sub_dependency_cache
        ) = solved_result
        dependency_cache.update(sub_dependency_cache)
        if sub_errors:
            errors.extend(sub_errors)
            continue
        if sub_dependant.use_cache and sub_dependant.cache_key in dependency_cache:
            solved = dependency_cache[sub_dependant.cache_key]
        elif is_gen_callable(call):
            solved = solve_generator(
                call=call, stack=stack, sub_values=sub_values
            )
        else:
            solved = call(**sub_values)
        if sub_dependant.name is not None:
            values[sub_dependant.name] = solved
        if sub_dependant.cache_key not in dependency_cache:
            dependency_cache[sub_dependant.cache_key] = solved
    path_values, path_errors = request_params_to_args(
        dependant.path_params, path_params, False
    )
    query_values, query_errors = request_params_to_args(
        dependant.query_params, request.args.to_dict(), True
    )
    header_values, header_errors = request_params_to_args(
        dependant.header_params, dict(request.headers), True
    )
    cookie_values, cookie_errors = request_params_to_args(
        dependant.cookie_params, request.cookies.to_dict(), False
    )
    values.update(path_values)
    values.update(query_values)
    values.update(header_values)
    values.update(cookie_values)
    errors += query_errors + header_errors + cookie_errors + path_errors
    if dependant.body_params:
        (
            body_values,
            body_errors
        ) = request_body_to_args(
            required_params=dependant.body_params, received_body=body, get_list=is_body_form
        )
        values.update(body_values)
        errors.extend(body_errors)

    if dependant.response_param_name:
        values[dependant.response_param_name] = response

    return values, errors, dependency_cache


def request_body_to_args(
    required_params: List[ModelField],
    received_body: Optional[Union[Dict[str, Any]]],
    get_list: bool = False
):
    values = {}
    errors = []
    if required_params:
        field = required_params[0]
        field_info = field.field_info
        embed = getattr(field_info, "embed", None)
        field_alias_omitted = len(required_params) == 1 and not embed
        # not form
        if field_alias_omitted:
            # 是否嵌入 是就整个解析
            received_body = {field.alias: received_body}

        for field in required_params:
            loc: Tuple[str, ...]
            if field_alias_omitted:
                loc = ("body",)
            else:
                loc = ("body", field.alias)

            value: Optional[Any] = None
            if received_body is not None:
                if (
                    field.shape in sequence_shapes or field.type_ in sequence_types
                ) and get_list:
                    # 只有form才会走到这里, form embed都为true
                    value = received_body.getlist(field.alias)
                else:
                    try:
                        value = received_body.get(field.alias)
                    except AttributeError:
                        errors.append(get_missing_field_error(loc))
                        continue
            if (
                    value is None
                    or (isinstance(field_info, params.Form) and value == "")
                    or (
                    isinstance(field_info, params.Form)
                    and field.shape in sequence_shapes
                    and len(value) == 0
                )
            ):
                if field.required:
                    errors.append(get_missing_field_error(loc))
                else:
                    values[field.name] = deepcopy(field.default)
                continue

            # todo upload file
            # if (
            #     isinstance(field_info, params.File)
            #     and lenient_issubclass(field.type_, bytes)
            #     # and isinstance(value, )
            # )
            v_, errors_ = field.validate(value, values, loc=loc)
            if isinstance(errors_, ErrorWrapper):
                errors.append(errors_)
            elif isinstance(errors_, list):
                errors.extend(errors_)
            else:
                values[field.name] = v_
    return values, errors


def request_params_to_args(
    required_params: Sequence[ModelField],
    received_params: Any,
    get_list: bool = False
) -> Tuple[Dict[str, Any], List[ErrorWrapper]]:
    values = {}
    errors = []
    for field in required_params:
        # headers, args
        if is_scalar_sequence_field(field) and get_list:
            value = received_params.getList(field.alias) or field.default
        else:
            value = received_params.get(field.alias)
        field_info = field.field_info
        assert isinstance(
            field_info, params.Param
        ), "Params must be subclasses of Param"
        if value is None:
            if field.required:
                errors.append(
                    ErrorWrapper(
                        MissingError(), loc=(field_info.in_.value, field.alias)
                    )
                )
            else:
                values[field.name] = deepcopy(field.default)
            continue
        v_, errors_ = field.validate(
            value, values, loc=(field_info.in_.value, field.alias)
        )
        if isinstance(errors_, ErrorWrapper):
            errors.append(errors_)
        elif isinstance(errors_, list):
            errors.extend(errors_)
        else:
            values[field.name] = v_
    return values, errors
