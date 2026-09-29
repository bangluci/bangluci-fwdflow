from pydantic import BaseModel, ValidationError

from app.envelope import AppError


def validate_patch(schema: type[BaseModel], current: dict, payload: dict) -> dict:
    """PATCH: trộn giá trị hiện tại với payload rồi kiểm cả bản ghi bằng schema đầy đủ; từ chối trường lạ."""
    unknown = payload.keys() - schema.model_fields.keys()
    if unknown:
        raise AppError("VALIDATION_ERROR", f"Trường không hợp lệ: {', '.join(sorted(unknown))}", 422)
    try:
        return schema.model_validate({**current, **payload}).model_dump()
    except ValidationError as exc:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise AppError("VALIDATION_ERROR", "Dữ liệu không hợp lệ", 422, details) from exc
