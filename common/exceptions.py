from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    status_code = response.status_code

    if status_code == 401:
        code = "UNAUTHORIZED"
        message = "인증이 필요합니다."

    elif status_code == 403:
        code = "FORBIDDEN"
        message = "접근 권한이 없습니다."

    elif status_code == 404:
        code = "NOT_FOUND"
        message = "요청한 리소스를 찾을 수 없습니다."

    else:
        code = "INVALID_REQUEST"
        message = "요청을 처리할 수 없습니다."

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "field": None,
            "requestId": request_id,
        }
    }

    return response


class TriptailorAPIException(APIException):
    status_code = 400
    default_code = "INVALID_REQUEST"
    default_detail = "요청을 처리할 수 없습니다."

    def __init__(
        self,
        code=None,
        message=None,
        field=None,
        status_code=None,
    ):
        if status_code is not None:
            self.status_code = status_code

        self.error_code = code or self.default_code
        self.error_message = message or self.default_detail
        self.field = field

        super().__init__(detail=self.error_message)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    if isinstance(exc, TriptailorAPIException):
        response.data = {
            "error": {
                "code": exc.error_code,
                "message": exc.error_message,
                "field": exc.field,
                "requestId": request_id,
            }
        }
        return response

    status_code = response.status_code

    if status_code == 401:
        code = "UNAUTHORIZED"
        message = "인증이 필요합니다."
    elif status_code == 403:
        code = "FORBIDDEN"
        message = "접근 권한이 없습니다."
    elif status_code == 404:
        code = "NOT_FOUND"
        message = "요청한 리소스를 찾을 수 없습니다."
    else:
        code = "INVALID_REQUEST"
        message = "요청을 처리할 수 없습니다."

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "field": None,
            "requestId": request_id,
        }
    }

    return response