from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Annotated, Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

BASE_URL = os.environ.get("PET_HOSPITAL_URL", "http://127.0.0.1:8080").rstrip("/")

mcp = FastMCP("pet-hospital")
logger = logging.getLogger("pet-hospital-mcp")
logger.addHandler(logging.NullHandler())

APP_JSON = "application/json"
RETRY_STATUS = {429, 500, 502, 503, 504}
ERROR_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    429: "rate_limited",
    500: "server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}

# 测试可注入 httpx.MockTransport。
_TRANSPORT: httpx.AsyncBaseTransport | None = None


class PetHospitalError(RuntimeError):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.status is not None:
            payload["status"] = self.status
        return payload


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else f"HTTP {response.status_code}"
    if isinstance(data, dict):
        for key in ("message", "error", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return str(data)[:500]


async def _api_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{BASE_URL}{path}"
    started = time.perf_counter()
    last_error: PetHospitalError | None = None

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=30.0, transport=_TRANSPORT
            ) as client:
                response = await client.request(
                    method, url, params=params, json=payload
                )
        except httpx.TimeoutException as exc:
            last_error = PetHospitalError(
                "timeout", f"上游宠物医院接口超时: {exc}"
            )
        except httpx.HTTPError as exc:
            last_error = PetHospitalError(
                "network_error", f"无法连接宠物医院服务: {exc}"
            )
        else:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s %.1fms",
                method,
                path,
                response.status_code,
                duration_ms,
            )
            if response.status_code in RETRY_STATUS and attempt < 2:
                last_error = PetHospitalError(
                    ERROR_CODE_BY_STATUS.get(
                        response.status_code, f"http_{response.status_code}"
                    ),
                    _error_message(response),
                    response.status_code,
                )
                await asyncio.sleep(0.3 * (2**attempt))
                continue
            if response.status_code >= 400:
                raise PetHospitalError(
                    ERROR_CODE_BY_STATUS.get(
                        response.status_code, f"http_{response.status_code}"
                    ),
                    _error_message(response),
                    response.status_code,
                )

            try:
                result = response.json()
            except ValueError as exc:
                raise PetHospitalError(
                    "bad_response", "上游返回的不是合法 JSON（可能为 HTML 错误页）"
                ) from exc

            if not isinstance(result, dict):
                raise PetHospitalError("bad_response", "上游响应结构不是对象")
            code = result.get("code")
            if not (isinstance(code, int) and 200 <= code < 300):
                message = result.get("message") or result.get("error") or "unknown error"
                raise PetHospitalError(
                    "api_error", f"code={code}, message={message}", code
                )
            return result.get("data")

        if attempt < 2:
            await asyncio.sleep(0.3 * (2**attempt))

    assert last_error is not None
    raise last_error


def _fail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PetHospitalError):
        return {"ok": False, "error": exc.as_dict()}
    return {
        "ok": False,
        "error": {"code": "internal_error", "message": f"{type(exc).__name__}: {exc}"},
    }


@mcp.tool()
async def list_pets(
    species: str | None = None,
    doctor: str | None = None,
    status: str | None = None,
    disease: str | None = None,
    owner_name: str | None = None,
    owner_phone: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    order: Literal["asc", "desc"] | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=100)] = 10,
    min_cost: Annotated[int, Field(ge=0)] | None = None,
    max_cost: Annotated[int, Field(ge=0)] | None = None,
) -> dict:
    """查询宠物档案列表，支持按种类、医生、状态、疾病、主人、关键词筛选，以及排序和分页。

    参数：
    - species: 种类（犬、猫、兔、鸟、仓鼠、爬宠、其他）
    - status: 就诊状态（待就诊/就诊中/住院中/已康复/慢性病随访）
    - order: 排序方向，仅允许 asc 或 desc
    - page: 页码，从 1 开始
    - page_size: 每页条数，范围 1-100
    """
    params: dict[str, Any] = {
        "page": page,
        "pageSize": page_size,
    }
    if species is not None:
        params["species"] = species
    if doctor is not None:
        params["doctor"] = doctor
    if status is not None:
        params["status"] = status
    if disease is not None:
        params["disease"] = disease
    if owner_name is not None:
        params["ownerName"] = owner_name
    if owner_phone is not None:
        params["ownerPhone"] = owner_phone
    if q is not None:
        params["q"] = q
    if sort_by is not None:
        params["sortBy"] = sort_by
    if order is not None:
        params["order"] = order
    if min_cost is not None:
        params["min"] = min_cost
    if max_cost is not None:
        params["max"] = max_cost

    try:
        data = await _api_request("GET", "/api/v1/pets", params=params)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001 - MCP 工具边界
        return _fail(exc)


@mcp.tool()
async def get_pet(pet_id: str) -> dict:
    """按宠物档案 ID 查询详情（包含历史病历与消费明细）。"""
    try:
        data = await _api_request("GET", f"/api/v1/pets/{pet_id}")
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
async def create_pet(
    name: str,
    species: str,
    owner_name: str,
    owner_phone: str,
    doctor: str,
    disease: str,
    breed: str | None = None,
    gender: Literal["公", "母"] | None = None,
    age_months: Annotated[int, Field(ge=0)] | None = None,
    color: str | None = None,
    chip_no: str | None = None,
    owner_addr: str | None = None,
    status: Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"] | None = None,
    allergy: str | None = None,
    note: str | None = None,
) -> dict:
    """新增宠物档案。

    必填：name、species、owner_name、owner_phone、doctor、disease。
    gender 仅允许“公/母”；status 仅允许指定枚举；age_months 不能为负数。
    """
    payload: dict[str, Any] = {
        "name": name,
        "species": species,
        "ownerName": owner_name,
        "ownerPhone": owner_phone,
        "doctor": doctor,
        "disease": disease,
    }
    optional = {
        "breed": breed,
        "gender": gender,
        "ageMonths": age_months,
        "color": color,
        "chipNo": chip_no,
        "ownerAddr": owner_addr,
        "status": status,
        "allergy": allergy,
        "note": note,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})

    try:
        data = await _api_request("POST", "/api/v1/pets", payload=payload)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
async def delete_pet(pet_id: str) -> dict:
    """按宠物档案 ID 删除档案。"""
    try:
        data = await _api_request("DELETE", f"/api/v1/pets/{pet_id}")
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


@mcp.tool()
async def get_stats() -> dict:
    """获取经营统计（档案数、总收入、种类/医生排行等）。"""
    try:
        data = await _api_request("GET", "/api/v1/stats")
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
