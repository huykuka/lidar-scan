"""Recording stream WebSocket command and event schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt


class StreamStartCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start"]
    frameIndex: StrictInt


class StreamSeekCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["seek"]
    frameIndex: StrictInt
