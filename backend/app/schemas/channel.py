from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelCreate(BaseModel):
    telegram_id: int | None = Field(None, ge=1)
    channel_ref: str | None = Field(
        None,
        min_length=2,
        max_length=512,
        description="Username (@name) или ссылка (https://t.me/name)",
    )
    username: str | None = None
    title: str | None = None
    description: str | None = None
    topic_search: str | None = Field(None, max_length=512)
    extra_conditions: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def validate_identity(self) -> "ChannelCreate":
        if self.telegram_id is None and not (self.channel_ref or "").strip():
            raise ValueError("Укажите telegram_id или channel_ref")
        return self


class ChannelCollectRequest(BaseModel):
    channel_ref: str | None = Field(None, min_length=2, max_length=512)
    topic: str | None = Field(None, min_length=1, max_length=512)
    extra_conditions: str | None = Field(None, max_length=2000)


class ChannelCollectResponse(BaseModel):
    status: str
    message: str
    channel_id: int
    created_new_channel: bool = False
    background_job_id: str | None = None
    needs_review: bool = False
    reason: str | None = None
    hints: list[str] = Field(default_factory=list)


class ChannelCreateResult(BaseModel):
    id: int
    username: str | None = None
    sync_status: str | None = None
    already_exists: bool = False
    message: str


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    title: str | None
    description: str | None
    topic_search: str | None = None
    created_at: datetime | None = None
    sync_status: str | None = None
    extra_conditions: str | None = None


class ChannelListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ChannelRead] = Field(default_factory=list)
