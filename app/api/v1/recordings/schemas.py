"""Recording stream WebSocket command and event schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt


class StreamStartCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start"]
    frameIndex: StrictInt | None = None


class StreamSeekCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["seek"]
    frameIndex: StrictInt


class StreamPauseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pause"]
