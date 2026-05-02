from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    telegram_id: int = Field(..., ge=1)
    username: str | None = None
    title: str | None = None
    description: str | None = None


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    title: str | None
    description: str | None
