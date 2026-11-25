from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

AffiliationType = Literal["university", "institute", "company", "personal", "other"]


class SubmissionCreate(BaseModel):
    """使用登记表单。website 是蜜罐字段：正常页面不可见，被填充即视为爬虫。"""

    name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    affiliation_type: AffiliationType
    organization: str = Field(min_length=1, max_length=200)
    info: Optional[str] = Field(default=None, max_length=500)
    email: Optional[EmailStr] = None
    website: Optional[str] = None

    @field_validator("name", "organization")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空白")
        return value

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("info")
    @classmethod
    def clean_info(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None
