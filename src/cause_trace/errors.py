"""业务错误码体系（Spec 6.3）。"""

from __future__ import annotations


class CauseTraceError(Exception):
    """所有业务异常的基类，携带错误码供接口层统一序列化。"""

    code = "SYS_INTERNAL"
    http_status = 500

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class InvalidIntentError(CauseTraceError):
    code = "BIZ_INVALID_INTENT"
    http_status = 400


class ConservationError(CauseTraceError):
    """守恒校验失败：禁止出图与入报告（ADR-03）。"""

    code = "BIZ_CONSERVATION_FAILED"
    http_status = 422


class UnsupportedDecompositionError(CauseTraceError):
    code = "BIZ_UNSUPPORTED_DECOMPOSITION"
    http_status = 400


class ReportPayloadError(CauseTraceError):
    code = "BIZ_INVALID_REPORT_PAYLOAD"
    http_status = 400


class SandboxPolicyError(CauseTraceError):
    """沙箱策略拦截，`code` 由调用方指定为 SBX_* 具体错误码。"""

    code = "SBX_POLICY_VIOLATION"
    http_status = 403


class SandboxUnavailableError(CauseTraceError):
    code = "SBX_UNAVAILABLE"
    http_status = 503
